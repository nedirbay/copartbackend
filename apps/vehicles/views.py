from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from users.permissions import IsAdminUserRole
from .models import Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument
from .serializers import (
    VehicleSerializer,
    VehicleHistoryLogSerializer,
    VehicleExpenseSerializer,
    VehicleDocumentSerializer,
    VehicleUpdateStatusLocationSerializer,
    VehicleHandoverSerializer
)
from .services import (
    create_vehicle_service,
    update_vehicle_status_location_service,
    handover_vehicle_service,
    add_vehicle_expense_service,
    add_vehicle_document_service
)

User = get_user_model()

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
        return Vehicle.objects.filter(current_owner=user).order_by('-created_at')

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
        
        # Check permissions: Admin or assigned owner
        if not (user.is_admin_role or vehicle.current_owner == user):
            raise PermissionDenied("Siziň bu awtoulagyň ýagdaýyny üýtgetmäge hukugyňyz ýok.")

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

    @action(detail=True, methods=['post'], url_path='handover')
    def handover(self, request, vin=None):
        """
        Kabul ediş-tabşyryş (Handover): Transfer vehicle to an employee.
        """
        vehicle = self.get_object()
        user = request.user

        if not (user.is_admin_role or vehicle.current_owner == user):
            raise PermissionDenied("Siziň bu awtoulagy tabşyrmaga hukugyňyz ýok.")

        serializer = VehicleHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = get_object_or_404(User, id=serializer.validated_data['employee_id'])
        if employee.role != User.Role.EMPLOYEE and not employee.is_admin_role:
            return Response({"error": "Invalid target employee."}, status=status.HTTP_400_BAD_REQUEST)

        updated_vehicle, log = handover_vehicle_service(
            vehicle=vehicle,
            new_owner_user=employee,
            note=serializer.validated_data.get('note', ''),
            user=user
        )

        return Response({
            'message': f"Awtoulag {employee.username} işgäre üstünlikli tabşyryldy.",
            'vehicle': VehicleSerializer(updated_vehicle).data,
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
