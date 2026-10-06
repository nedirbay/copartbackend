from django.db.models import Q, Sum, Count
from rest_framework import viewsets, generics, status, permissions


from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from users.permissions import IsAdminUserRole
from .models import (
    Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType
)
from .serializers import (
    VehicleSerializer,
    VehicleHistoryLogSerializer,
    VehicleExpenseSerializer,
    VehicleDocumentSerializer,
    VehicleUpdateStatusLocationSerializer,
    VehicleHandoverSerializer,
    DynamicVehicleStatusSerializer,
    DynamicVehicleLocationSerializer,
    MakeSerializer,
    VehicleModelSerializer,
    CurrencySerializer,
    ExpenseTypeSerializer
)
from .services import (
    create_vehicle_service,
    update_vehicle_status_location_service,
    handover_vehicle_service,
    add_vehicle_expense_service,
    add_vehicle_document_service
)

User = get_user_model()

class BaseDictionaryViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminUserRole()]

class DynamicVehicleStatusViewSet(BaseDictionaryViewSet):
    queryset = DynamicVehicleStatus.objects.all()
    serializer_class = DynamicVehicleStatusSerializer

class DynamicVehicleLocationViewSet(BaseDictionaryViewSet):
    queryset = DynamicVehicleLocation.objects.all()
    serializer_class = DynamicVehicleLocationSerializer

class MakeViewSet(BaseDictionaryViewSet):
    queryset = Make.objects.all().order_by('name')
    serializer_class = MakeSerializer

class VehicleModelViewSet(BaseDictionaryViewSet):
    queryset = VehicleModel.objects.all().order_by('name')
    serializer_class = VehicleModelSerializer

    def get_queryset(self):
        qs = VehicleModel.objects.all().order_by('name')
        make_id = self.request.query_params.get('make_id')
        make_name = self.request.query_params.get('make')
        if make_id:
            qs = qs.filter(make_id=make_id)
        elif make_name:
            qs = qs.filter(make__name__iexact=make_name)
        return qs

class CurrencyViewSet(BaseDictionaryViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer

class ExpenseTypeViewSet(BaseDictionaryViewSet):
    queryset = ExpenseType.objects.all().order_by('name')
    serializer_class = ExpenseTypeSerializer


def check_vehicle_write_permission(vehicle, user):
    """
    Enforces business rules:
    1) Maşyn Berkitmek (is_handed_over = False):
       - Assigned employee can view, but CANNOT add/edit (read-only).
       - Admin CAN add/edit.
    2) Maşyn Tabşyrmak (is_handed_over = True):
       - Handed-over employee (current_owner) CAN add/edit.
       - Admin CANNOT add/edit (read-only).
    """
    if vehicle.is_handed_over:
        if vehicle.current_owner != user:
            if user.is_admin_role:
                raise PermissionDenied("Awtoulag işgäre tabşyrylan. Tabşyrylan soň diňe jogapkär işgär üýtgeşme girizip biler (Admin okaýar).")
            raise PermissionDenied("Siziň bu awtoulagy üýtgetmäge hukugyňyz ýok.")
    else:
        if not user.is_admin_role:
            if vehicle.current_owner == user:
                raise PermissionDenied("Awtoulag size diňe berkidilen (tabşyrylmadyk). Diňe görmek rugsadyňyz bar.")
            raise PermissionDenied("Siziň bu awtoulagy üýtgetmäge hukugyňyz ýok.")


class VehicleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing vehicles.
    Admin sees all vehicles and can register new vehicles.
    Employees see only vehicles assigned to them (current_owner).
    """
    queryset = Vehicle.objects.all().order_by('-created_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'vin'

    def get_queryset(self):
        user = self.request.user
        if user.is_admin_role:
            return Vehicle.objects.all().order_by('-created_at')
        return Vehicle.objects.filter(
            Q(current_owner=user) | Q(pending_handover_owner=user)
        ).distinct().order_by('-created_at')



    def create(self, request, *args, **kwargs):
        # Only admin can create new vehicles
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin täze awtoulag hasaba alyp biler.")
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        vehicle = create_vehicle_service(
            validated_data=serializer.validated_data,
            created_by_user=request.user
        )
        output_serializer = VehicleSerializer(vehicle)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='update-status-location')
    def update_status_location(self, request, vin=None):
        """
        Update vehicle status or location, generating a real-time history log.
        """
        vehicle = self.get_object()
        user = request.user
        
        check_vehicle_write_permission(vehicle, user)

        serializer = VehicleUpdateStatusLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_vehicle, log = update_vehicle_status_location_service(
            vehicle=vehicle,
            status=serializer.validated_data.get('status'),
            location=serializer.validated_data.get('location'),
            note=serializer.validated_data.get('note', ''),
            user=user
        )

        return Response({
            'vehicle': VehicleSerializer(updated_vehicle).data,
            'log': VehicleHistoryLogSerializer(log).data
        })

    @action(detail=True, methods=['post'], url_path='assign')
    def assign(self, request, vin=None):
        """
        Işgäre Berkitmek (Assign): Admin assigns/changes assigned employee (current_owner).
        """
        vehicle = self.get_object()
        user = request.user

        if not user.is_admin_role:
            raise PermissionDenied("Diňe Admin ulanyjy awtoulagy işgäre berkidip biler.")

        if vehicle.is_handed_over:
            raise PermissionDenied("Awtoulag eýýäm işgäre tabşyrylan. Berkitmäni üýtgetmäge rugsadyňyz ýok.")


        serializer = VehicleHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = get_object_or_404(User, id=serializer.validated_data['employee_id'])
        vehicle.current_owner = employee
        vehicle.save()

        log = VehicleHistoryLog.objects.create(
            vehicle=vehicle,
            status=vehicle.status,
            location=vehicle.location,
            owner=employee,
            changed_by=user,
            note=serializer.validated_data.get('note', '') or f"Awtoulag Admin tarapyndan {employee.username} işgäre berkidildi."
        )

        return Response({
            'message': f"Awtoulag {employee.username} işgäre berkidildi.",
            'vehicle': VehicleSerializer(vehicle).data,
            'log': VehicleHistoryLogSerializer(log).data
        })

    @action(detail=True, methods=['post'], url_path='handover')
    def handover(self, request, vin=None):
        """
        Kabul ediş-tabşyryş Başlatmak (Initiate Handover):
        Employee initiates handover request to a target employee (pending_handover_owner).
        Admin CANNOT initiate handover.
        """
        vehicle = self.get_object()
        user = request.user

        if user.is_admin_role:
            raise PermissionDenied("Admin ulanyjy Handover edip bilmez, diňe işgäre berkitmeli (Assign).")

        if vehicle.current_owner != user:
            raise PermissionDenied("Siziň bu awtoulagy tabşyrmaga hukugyňyz ýok.")

        serializer = VehicleHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = get_object_or_404(User, id=serializer.validated_data['employee_id'])
        vehicle.pending_handover_owner = employee
        vehicle.save()

        log = VehicleHistoryLog.objects.create(
            vehicle=vehicle,
            status=vehicle.status,
            location=vehicle.location,
            owner=vehicle.current_owner,
            changed_by=user,
            note=serializer.validated_data.get('note', '') or f"Handover haýyşy ugradyldy: {employee.username} üçin."
        )

        return Response({
            'message': f"Awtoulagy tabşyryş haýyşy {employee.username} işgäre ugradyldy. Tassyklaýyşa garaşylýar.",
            'vehicle': VehicleSerializer(vehicle).data,
            'log': VehicleHistoryLogSerializer(log).data
        })

    @action(detail=True, methods=['post'], url_path='confirm-handover')
    def confirm_handover(self, request, vin=None):
        """
        Kabul ediş-tabşyryş Tassyklaýyş (Confirm Handover):
        Target employee confirms receiving the vehicle.
        """
        vehicle = self.get_object()
        user = request.user

        if vehicle.pending_handover_owner != user:
            raise PermissionDenied("Siziň bu awtoulagy kabul etmäge / tassyklaýyş geçirmäge hukugyňyz ýok.")

        vehicle.current_owner = user
        vehicle.is_handed_over = True
        vehicle.pending_handover_owner = None
        vehicle.save()

        log = VehicleHistoryLog.objects.create(
            vehicle=vehicle,
            status=vehicle.status,
            location=vehicle.location,
            owner=user,
            changed_by=user,
            note=f"Awtoulag {user.username} tarapyndan kabul edildi we tassyklandy (Handover confirmed)."
        )

        return Response({
            'message': "Awtoulag üstünlikli kabul edildi we tassyklandy!",
            'vehicle': VehicleSerializer(vehicle).data,
            'log': VehicleHistoryLogSerializer(log).data
        })


    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, vin=None):
        """
        Get all history logs for a vehicle.
        """
        vehicle = self.get_object()
        logs = vehicle.history_logs.all()
        serializer = VehicleHistoryLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='reports/summary')
    def reports_summary(self, request):
        """
        Get aggregated report analytics & KPIs filtered by date / period.
        """
        user = request.user
        vehicle_qs = self.get_queryset()

        period_type = request.query_params.get('period_type', 'all')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        date = request.query_params.get('date')
        start_year = request.query_params.get('start_year')
        end_year = request.query_params.get('end_year')
        year = request.query_params.get('year')
        start_month = request.query_params.get('start_month')
        end_month = request.query_params.get('end_month')
        month = request.query_params.get('month')

        if period_type == 'day' and date:
            vehicle_qs = vehicle_qs.filter(created_at__date=date)
        elif period_type == 'day_range':
            if start_date:
                vehicle_qs = vehicle_qs.filter(created_at__date__gte=start_date)
            if end_date:
                vehicle_qs = vehicle_qs.filter(created_at__date__lte=end_date)
        elif period_type == 'month' and month:
            try:
                parts = month.split('-')
                vehicle_qs = vehicle_qs.filter(created_at__year=int(parts[0]), created_at__month=int(parts[1]))
            except (ValueError, IndexError):
                pass
        elif period_type == 'month_range':
            if start_month:
                try:
                    parts = start_month.split('-')
                    vehicle_qs = vehicle_qs.filter(created_at__year__gte=int(parts[0]))
                except (ValueError, IndexError):
                    pass
            if end_month:
                try:
                    parts = end_month.split('-')
                    vehicle_qs = vehicle_qs.filter(created_at__year__lte=int(parts[0]))
                except (ValueError, IndexError):
                    pass
        elif period_type == 'year' and year:
            try:
                vehicle_qs = vehicle_qs.filter(created_at__year=int(year))
            except ValueError:
                pass
        elif period_type == 'year_range':
            if start_year:
                try:
                    vehicle_qs = vehicle_qs.filter(created_at__year__gte=int(start_year))
                except ValueError:
                    pass
            if end_year:
                try:
                    vehicle_qs = vehicle_qs.filter(created_at__year__lte=int(end_year))
                except ValueError:
                    pass

        # Calculate KPIs
        total_vehicles = vehicle_qs.count()
        expenses_qs = VehicleExpense.objects.filter(vehicle__in=vehicle_qs)
        total_expenses_usd = expenses_qs.aggregate(total=Sum('amount'))['total'] or 0

        # Status breakdown
        by_status = list(vehicle_qs.values('status').annotate(count=Count('vin')).order_by('-count'))
        
        # Location breakdown
        by_location = list(vehicle_qs.values('location').annotate(count=Count('vin')).order_by('-count'))

        # Expense breakdown by Title
        by_expense_title = list(expenses_qs.values('title').annotate(total_amount=Sum('amount'), count=Count('id')).order_by('-total_amount'))

        # Expense breakdown by Stage
        by_expense_stage = list(expenses_qs.values('stage').annotate(total_amount=Sum('amount')).order_by('-total_amount'))

        # Handover stats
        handed_over_count = vehicle_qs.filter(is_handed_over=True).count()
        assigned_count = vehicle_qs.filter(is_handed_over=False).count()

        # Vehicles table list
        vehicles_data = VehicleSerializer(vehicle_qs, many=True).data

        return Response({
            'kpis': {
                'total_vehicles': total_vehicles,
                'total_expenses_usd': f"{total_expenses_usd:.2f}",
                'handed_over_count': handed_over_count,
                'assigned_count': assigned_count
            },
            'by_status': by_status,
            'by_location': by_location,
            'by_expense_title': by_expense_title,
            'by_expense_stage': by_expense_stage,
            'vehicles': vehicles_data
        })



class VehicleExpenseViewSet(viewsets.ModelViewSet):
    """
    Manage expenses for a specific vehicle by VIN.
    """
    serializer_class = VehicleExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_vehicle(self):
        vin = self.kwargs.get('vehicle_vin')
        vehicle = get_object_or_404(Vehicle, vin=vin)
        user = self.request.user
        if not (user.is_admin_role or vehicle.current_owner == user):
            raise PermissionDenied("Siziň bu awtoulagyň çykdajylaryny görmäge hukugyňyz ýok.")
        return vehicle

    def get_queryset(self):
        vehicle = self.get_vehicle()
        return vehicle.expenses.all()

    def perform_create(self, serializer):
        vehicle = self.get_vehicle()
        check_vehicle_write_permission(vehicle, self.request.user)

        add_vehicle_expense_service(
            vehicle=vehicle,
            title=serializer.validated_data['title'],
            amount=serializer.validated_data['amount'],
            currency=serializer.validated_data.get('currency', 'USD'),
            description=serializer.validated_data.get('description', ''),
            stage=serializer.validated_data.get('stage', ''),
            user=self.request.user
        )


class VehicleDocumentViewSet(viewsets.ModelViewSet):
    """
    Upload and list photos & documents for a specific vehicle by VIN.
    """
    serializer_class = VehicleDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_vehicle(self):
        vin = self.kwargs.get('vehicle_vin')
        vehicle = get_object_or_404(Vehicle, vin=vin)
        user = self.request.user
        if not (user.is_admin_role or vehicle.current_owner == user):
            raise PermissionDenied("Siziň bu awtoulagyň resminamalaryny görmäge hukugyňyz ýok.")
        return vehicle

    def get_queryset(self):
        vehicle = self.get_vehicle()
        return vehicle.documents.all()

    def perform_create(self, serializer):
        vehicle = self.get_vehicle()
        check_vehicle_write_permission(vehicle, self.request.user)

        file_obj = self.request.FILES.get('file')
        if not file_obj:
            raise serializers.ValidationError({"file": "File is required."})

        add_vehicle_document_service(
            vehicle=vehicle,
            file_obj=file_obj,
            title=serializer.validated_data['title'],
            document_type=serializer.validated_data.get('document_type', 'PHOTO'),
            user=self.request.user
        )

