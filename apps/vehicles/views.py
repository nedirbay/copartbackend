import csv
import io
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, mixins, status, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from users.permissions import IsAdminUserRole
from .models import (
    Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument, Notification,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType,
    VehicleStatus, SYSTEM_STATUS_CODES, SYSTEM_LOCATION_CODES,
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
    ExpenseTypeSerializer,
    ReasonSerializer,
    RequiredReasonSerializer,
    ForceReassignSerializer,
    NotificationSerializer,
)
from .services import (
    create_vehicle_service,
    update_vehicle_status_location_service,
    add_vehicle_expense_service,
    add_vehicle_document_service,
    log_event,
    sync_make_model,
)
from .notifications import notify, admins

logger = logging.getLogger(__name__)
User = get_user_model()
Event = VehicleHistoryLog.Event


# ---------------------------------------------------------------- Sözlükler

class BaseDictionaryViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminUserRole()]


class CodeDictionaryViewSet(BaseDictionaryViewSet):
    """Ulgam kodlaryny we awtoulaglarda ulanylýan kodlary pozmak bolmaýar."""
    vehicle_field = None
    system_codes = set()

    def perform_destroy(self, instance):
        if instance.code in self.system_codes:
            raise ValidationError({"detail": "Ulgam ýazgysyny pozup bolmaýar."})
        used = Vehicle.objects.filter(**{self.vehicle_field: instance.code}).count()
        if used:
            raise ValidationError({"detail": f"Bu ýazgy {used} awtoulagda ulanylýar, pozup bolmaýar."})
        instance.delete()


class DynamicVehicleStatusViewSet(CodeDictionaryViewSet):
    queryset = DynamicVehicleStatus.objects.all()
    serializer_class = DynamicVehicleStatusSerializer
    vehicle_field = 'status'
    system_codes = SYSTEM_STATUS_CODES


class DynamicVehicleLocationViewSet(CodeDictionaryViewSet):
    queryset = DynamicVehicleLocation.objects.all()
    serializer_class = DynamicVehicleLocationSerializer
    vehicle_field = 'location'
    system_codes = SYSTEM_LOCATION_CODES


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

    def perform_create(self, serializer):
        serializer.save(rate_updated_at=timezone.now())

    def perform_update(self, serializer):
        rate_changed = 'usd_rate' in serializer.validated_data and \
            serializer.validated_data['usd_rate'] != serializer.instance.usd_rate
        if rate_changed:
            serializer.save(rate_updated_at=timezone.now())
        else:
            serializer.save()

    def perform_destroy(self, instance):
        if instance.code == 'USD':
            raise ValidationError({"detail": "Esasy walýutany (USD) pozup bolmaýar."})
        used = VehicleExpense.objects.filter(currency=instance.code).exists() or Vehicle.objects.filter(
            Q(purchase_currency=instance.code) | Q(sale_currency=instance.code)).exists()
        if used:
            raise ValidationError({"detail": "Bu walýuta ulanylýar, pozup bolmaýar."})
        instance.delete()


class ExpenseTypeViewSet(BaseDictionaryViewSet):
    queryset = ExpenseType.objects.all().order_by('name')
    serializer_class = ExpenseTypeSerializer


# ---------------------------------------------------------------- Hukuklar

def check_vehicle_write_permission(vehicle, user):
    """
    Enforces business rules:
    1) Maşyn Berkitmek (is_handed_over = False):
       - Assigned employee can view, but CANNOT add/edit (read-only).
       - Admin CAN add/edit.
    2) Maşyn Tabşyrmak (is_handed_over = True):
       - Handed-over employee (current_owner) CAN add/edit.
       - Admin CANNOT add/edit (read-only) — ýöne force-reassign / revoke-handover ulanyp biler.
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


def get_target_employee(employee_id, *, exclude_user=None):
    """
    Tabşyrylýan / berkidilýän ulanyjy diňe işjeň Işgär bolmaly.
    exclude_user — awtoulagy özüne tabşyrmagyň öňüni almak üçin.
    """
    employee = User.objects.filter(id=employee_id, role=User.Role.EMPLOYEE, is_active=True).first()
    if employee is None:
        raise ValidationError({"employee_id": "Işjeň işgär tapylmady."})
    if exclude_user is not None and employee == exclude_user:
        raise ValidationError({"employee_id": "Awtoulagy özüňize tabşyryp bilmersiňiz."})
    return employee


def can_read_vehicle_finance(vehicle, user):
    """Çykdajylary / resminamalary görmek: Admin, jogapkär ýa-da kabul etmäge garaşýan işgär."""
    return user.is_admin_role or vehicle.current_owner == user or vehicle.pending_handover_owner == user


def user_label(user):
    if user is None:
        return "—"
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


# ---------------------------------------------------------------- Hasabat süzgüçleri

def _parse_month(value):
    try:
        y, m = value.split('-')[:2]
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        return None


def _next_month(d):
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_period_filter(qs, params):
    """
    Döwür boýunça süzgüç. date_basis=created (hasaba alnan senesi, deslapky) ýa-da
    date_basis=sold (satylan senesi — diňe satylan awtoulaglar).
    """
    basis = params.get('date_basis', 'created')
    field = 'sold_at' if basis == 'sold' else 'created_at'
    if basis == 'sold':
        qs = qs.filter(sold_at__isnull=False)

    period_type = params.get('period_type', 'all')
    get = params.get

    if period_type == 'day' and get('date'):
        qs = qs.filter(**{f'{field}__date': get('date')})
    elif period_type == 'day_range':
        if get('start_date'):
            qs = qs.filter(**{f'{field}__date__gte': get('start_date')})
        if get('end_date'):
            qs = qs.filter(**{f'{field}__date__lte': get('end_date')})
    elif period_type == 'month' and get('month'):
        m = _parse_month(get('month'))
        if m:
            qs = qs.filter(**{f'{field}__date__gte': m, f'{field}__date__lt': _next_month(m)})
    elif period_type == 'month_range':
        start = _parse_month(get('start_month')) if get('start_month') else None
        end = _parse_month(get('end_month')) if get('end_month') else None
        if start:
            qs = qs.filter(**{f'{field}__date__gte': start})
        if end:
            qs = qs.filter(**{f'{field}__date__lt': _next_month(end)})
    elif period_type == 'year' and _int(get('year')):
        qs = qs.filter(**{f'{field}__year': _int(get('year'))})
    elif period_type == 'year_range':
        if _int(get('start_year')):
            qs = qs.filter(**{f'{field}__year__gte': _int(get('start_year'))})
        if _int(get('end_year')):
            qs = qs.filter(**{f'{field}__year__lte': _int(get('end_year'))})
    return qs


def _money(value):
    return f"{(value or 0):.2f}"


# ---------------------------------------------------------------- Awtoulaglar

class VehicleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing vehicles.
    Admin sees all vehicles and can register new vehicles.
    Employees see only vehicles assigned to them (current_owner).
    """
    queryset = Vehicle.objects.all().order_by('-created_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'vin'

    def get_queryset(self):
        user = self.request.user
        qs = Vehicle.objects.select_related('current_owner', 'pending_handover_owner')
        if not user.is_admin_role:
            qs = qs.filter(Q(current_owner=user) | Q(pending_handover_owner=user)).distinct()
        return qs.order_by('-created_at')

    def _out(self, vehicle):
        return VehicleSerializer(vehicle, context={'request': self.request}).data

    def create(self, request, *args, **kwargs):
        # Only admin can create new vehicles
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin täze awtoulag hasaba alyp biler.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner = serializer.validated_data.get('current_owner')
        if owner is not None and (not owner.is_active or owner.role != User.Role.EMPLOYEE) and owner != request.user:
            raise ValidationError({"current_owner": "Jogapkär işjeň işgär bolmaly."})

        vehicle = create_vehicle_service(
            validated_data=serializer.validated_data,
            created_by_user=request.user
        )
        if vehicle.current_owner and vehicle.current_owner != request.user:
            notify([vehicle.current_owner], "Täze awtoulag size berkidildi.", vehicle=vehicle, kind='ASSIGNED')
        return Response(self._out(vehicle), status=status.HTTP_201_CREATED)

    TRACKED_FIELDS = {
        'title': 'Ady', 'make': 'Marka', 'model': 'Model', 'year': 'Ýyly', 'color': 'Reňki',
        'mileage': 'Ýörän ýoly', 'lot_number': 'Lot', 'auction_date': 'Auksion senesi',
        'container_number': 'Konteýner', 'eta': 'ETA',
        'purchase_price': 'Satyn alyş bahasy', 'purchase_currency': 'Satyn alyş walýutasy',
        'sale_price': 'Satuw bahasy', 'sale_currency': 'Satuw walýutasy',
        'buyer_name': 'Alyjy', 'buyer_phone': 'Alyjynyň telefony', 'buyer_note': 'Alyjy bellik',
    }

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Admin üçin hem: tabşyrylan awtoulagy Admin diňe okaýar
        check_vehicle_write_permission(instance, request.user)

        old_status = instance.status
        old_location = instance.location
        old_owner = instance.current_owner
        old_values = {f: getattr(instance, f) for f in self.TRACKED_FIELDS}

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Jogapkäri diňe Admin we diňe tabşyrylmadyk awtoulagda üýtgedip biler (berkitmek bilen deň)
        new_owner = serializer.validated_data.get('current_owner', old_owner)
        if new_owner != old_owner:
            if not request.user.is_admin_role or instance.is_handed_over:
                raise PermissionDenied("Jogapkäri üýtgetmäge hukugyňyz ýok.")
            if new_owner is not None and not new_owner.is_active:
                raise ValidationError({"current_owner": "Işjeň däl ulanyjy jogapkär bolup bilmez."})

        self.perform_update(serializer)

        updated = self.get_object()
        sync_make_model(updated.make, updated.model)

        changes = []
        if old_status != updated.status:
            changes.append(f"Status: {old_status} -> {updated.status}")
        if old_location != updated.location:
            changes.append(f"Ýerleşýän ýeri: {old_location} -> {updated.location}")
        if old_owner != updated.current_owner:
            new_owner_name = updated.current_owner.username if updated.current_owner else "Bellenilmegen"
            changes.append(f"Jogapkär: {new_owner_name}")
        for field, label in self.TRACKED_FIELDS.items():
            if old_values[field] != getattr(updated, field):
                changes.append(f"{label}: {old_values[field] or '—'} -> {getattr(updated, field) or '—'}")

        if changes:
            event = Event.STATUS if (old_status != updated.status or old_location != updated.location) else Event.UPDATED
            log_event(updated, event, "Awtoulag maglumatlary üýtgedildi: " + ", ".join(changes), user=request.user)

        if old_owner != updated.current_owner and updated.current_owner:
            notify([updated.current_owner], "Awtoulag size berkidildi.", vehicle=updated, kind='ASSIGNED')
        if old_status != updated.status:
            self._notify_status(updated, request.user)

        return Response(self._out(updated))

    def _notify_status(self, vehicle, user):
        msg = f"Status üýtgedildi: {vehicle.status} / {vehicle.location} ({user_label(user)})"
        recipients = [vehicle.current_owner] if user.is_admin_role else admins()
        notify(recipients, msg, vehicle=vehicle, kind='STATUS', exclude=user)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin awtoulagy pozup biler.")
        return super().destroy(request, *args, **kwargs)

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

        old_status = vehicle.status
        updated_vehicle, log = update_vehicle_status_location_service(
            vehicle=vehicle,
            status=serializer.validated_data.get('status'),
            location=serializer.validated_data.get('location'),
            note=serializer.validated_data.get('note', ''),
            user=user
        )
        if old_status != updated_vehicle.status:
            self._notify_status(updated_vehicle, user)

        return Response({
            'vehicle': self._out(updated_vehicle),
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
            raise PermissionDenied("Awtoulag eýýäm işgäre tabşyrylan. Täzeden berkitmek üçin 'Mejbury täzeden berkitmek' ulanyň.")

        serializer = VehicleHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = get_target_employee(serializer.validated_data['employee_id'])
        vehicle.current_owner = employee
        vehicle.pending_handover_owner = None
        vehicle.save()

        log = log_event(
            vehicle, Event.ASSIGNED,
            serializer.validated_data.get('note', '') or f"Awtoulag Admin tarapyndan {employee.username} işgäre berkidildi.",
            user=user, owner=employee,
        )
        notify([employee], "Awtoulag size berkidildi.", vehicle=vehicle, kind='ASSIGNED')

        return Response({
            'message': f"Awtoulag {employee.username} işgäre berkidildi.",
            'vehicle': self._out(vehicle),
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

        employee = get_target_employee(serializer.validated_data['employee_id'], exclude_user=user)
        previous_target = vehicle.pending_handover_owner
        vehicle.pending_handover_owner = employee
        vehicle.save()

        log = log_event(
            vehicle, Event.HANDOVER_REQUESTED,
            serializer.validated_data.get('note', '') or f"Handover haýyşy ugradyldy: {employee.username} üçin.",
            user=user,
        )
        notify([employee], f"{user_label(user)} size awtoulagy tabşyrmak isleýär. Kabul ediň ýa-da ret ediň.",
               vehicle=vehicle, kind='HANDOVER_REQUESTED')
        if previous_target and previous_target != employee:
            notify([previous_target], "Size gönükdirilen tabşyryş haýyşy başga işgäre geçirildi.",
                   vehicle=vehicle, kind='HANDOVER_CANCELLED')

        return Response({
            'message': f"Awtoulagy tabşyryş haýyşy {employee.username} işgäre ugradyldy. Tassyklaýyşa garaşylýar.",
            'vehicle': self._out(vehicle),
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

        previous_owner = vehicle.current_owner
        vehicle.current_owner = user
        vehicle.is_handed_over = True
        vehicle.pending_handover_owner = None
        vehicle.save()

        log = log_event(
            vehicle, Event.HANDOVER_CONFIRMED,
            f"Awtoulag {user.username} tarapyndan kabul edildi we tassyklandy (Handover confirmed).",
            user=user, owner=user,
        )
        notify([previous_owner, *admins()], f"Awtoulag {user_label(user)} tarapyndan kabul edildi.",
               vehicle=vehicle, kind='HANDOVER_CONFIRMED', exclude=user)

        return Response({
            'message': "Awtoulag üstünlikli kabul edildi we tassyklandy!",
            'vehicle': self._out(vehicle),
            'log': VehicleHistoryLogSerializer(log).data
        })

    @action(detail=True, methods=['post'], url_path='reject-handover')
    def reject_handover(self, request, vin=None):
        """Kabul etmeli işgär haýyşy ret edýär. Awtoulag öňki jogapkärde galýar."""
        vehicle = self.get_object()
        user = request.user
        if vehicle.pending_handover_owner != user:
            raise PermissionDenied("Size gönükdirilen tabşyryş haýyşy ýok.")

        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data['note']

        vehicle.pending_handover_owner = None
        vehicle.save()
        log = log_event(vehicle, Event.HANDOVER_REJECTED,
                        f"{user.username} tabşyryş haýyşyny ret etdi." + (f" Sebäbi: {note}" if note else ""), user=user)
        notify([vehicle.current_owner], f"{user_label(user)} tabşyryş haýyşyny ret etdi." + (f" Sebäbi: {note}" if note else ""),
               vehicle=vehicle, kind='HANDOVER_REJECTED')
        return Response({'message': "Haýyş ret edildi.", 'vehicle': self._out(vehicle),
                         'log': VehicleHistoryLogSerializer(log).data})

    @action(detail=True, methods=['post'], url_path='cancel-handover')
    def cancel_handover(self, request, vin=None):
        """Haýyşy ugradan jogapkär ýa-da Admin ony ýatyrýar."""
        vehicle = self.get_object()
        user = request.user
        if vehicle.pending_handover_owner is None:
            raise ValidationError({"detail": "Garaşylýan tabşyryş haýyşy ýok."})
        if vehicle.current_owner != user and not user.is_admin_role:
            raise PermissionDenied("Bu haýyşy ýatyrmaga hukugyňyz ýok.")

        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data['note']

        target = vehicle.pending_handover_owner
        vehicle.pending_handover_owner = None
        vehicle.save()
        log = log_event(vehicle, Event.HANDOVER_CANCELLED,
                        f"{user.username} tabşyryş haýyşyny ýatyrdy." + (f" Sebäbi: {note}" if note else ""), user=user)
        notify([target, vehicle.current_owner], "Tabşyryş haýyşy ýatyryldy.", vehicle=vehicle,
               kind='HANDOVER_CANCELLED', exclude=user)
        return Response({'message': "Haýyş ýatyryldy.", 'vehicle': self._out(vehicle),
                         'log': VehicleHistoryLogSerializer(log).data})

    @action(detail=True, methods=['post'], url_path='force-reassign')
    def force_reassign(self, request, vin=None):
        """
        Admin: awtoulagy (tabşyrylan bolsa hem) başga işgäre mejbury geçirýär.
        Işgär işden gitse ýa-da ýalňyş işgäre tabşyrylsa ulanylýar. Sebäbi hökmany.
        Tabşyryş ýagdaýy (is_handed_over) üýtgemeýär.
        """
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin mejbury täzeden berkidip biler.")
        vehicle = self.get_object()
        serializer = ForceReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = get_target_employee(serializer.validated_data['employee_id'])
        if employee == vehicle.current_owner:
            raise ValidationError({"employee_id": "Awtoulag eýýäm şu işgärde."})

        old_owner = vehicle.current_owner
        pending = vehicle.pending_handover_owner
        vehicle.current_owner = employee
        vehicle.pending_handover_owner = None
        vehicle.save()

        note = serializer.validated_data['note']
        log = log_event(vehicle, Event.REASSIGNED,
                        f"Admin awtoulagy {old_owner.username if old_owner else '—'} -> {employee.username} geçirdi. Sebäbi: {note}",
                        user=request.user, owner=employee)
        notify([employee], f"Admin awtoulagy size geçirdi. Sebäbi: {note}", vehicle=vehicle, kind='REASSIGNED')
        notify([old_owner, pending], f"Admin awtoulagy {user_label(employee)} işgäre geçirdi. Sebäbi: {note}",
               vehicle=vehicle, kind='REASSIGNED', exclude=employee)
        return Response({'message': f"Awtoulag {employee.username} işgäre geçirildi.", 'vehicle': self._out(vehicle),
                         'log': VehicleHistoryLogSerializer(log).data})

    @action(detail=True, methods=['post'], url_path='revoke-handover')
    def revoke_handover(self, request, vin=None):
        """Admin: tabşyrylan awtoulagyň dolandyryşyny yzyna alýar (is_handed_over=False). Sebäbi hökmany."""
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin dolandyryşy yzyna alyp biler.")
        vehicle = self.get_object()
        if not vehicle.is_handed_over:
            raise ValidationError({"detail": "Awtoulag tabşyrylmadyk, dolandyryş eýýäm Adminde."})
        serializer = RequiredReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data['note']

        pending = vehicle.pending_handover_owner
        vehicle.is_handed_over = False
        vehicle.pending_handover_owner = None
        vehicle.save()
        log = log_event(vehicle, Event.HANDOVER_REVOKED, f"Admin dolandyryşy yzyna aldy. Sebäbi: {note}", user=request.user)
        notify([vehicle.current_owner, pending], f"Admin awtoulagyň dolandyryşyny yzyna aldy. Sebäbi: {note}",
               vehicle=vehicle, kind='HANDOVER_REVOKED')
        return Response({'message': "Dolandyryş Admine gaýtaryldy.", 'vehicle': self._out(vehicle),
                         'log': VehicleHistoryLogSerializer(log).data})

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, vin=None):
        """
        Get all history logs for a vehicle.
        """
        vehicle = self.get_object()
        logs = vehicle.history_logs.select_related('owner', 'changed_by')
        return Response(VehicleHistoryLogSerializer(logs, many=True).data)

    @action(detail=True, methods=['get'], url_path='stage-durations')
    def stage_durations(self, request, vin=None):
        """Her status näçe gün dowam etdi (taryh ýazgylaryndan hasaplanýar)."""
        vehicle = self.get_object()
        logs = vehicle.history_logs.order_by('created_at').values('status', 'created_at')
        stages = []
        for log in logs:
            if not stages or stages[-1]['status'] != log['status']:
                if stages:
                    stages[-1]['ended_at'] = log['created_at']
                stages.append({'status': log['status'], 'started_at': log['created_at'], 'ended_at': None})
        now = timezone.now()
        for st in stages:
            end = st['ended_at'] or now
            st['days'] = round((end - st['started_at']).total_seconds() / 86400, 1)
        total = round((now - vehicle.created_at).total_seconds() / 86400, 1)
        return Response({'stages': stages, 'total_days': total})

    @action(detail=False, methods=['get'], url_path='vin-decode')
    def vin_decode(self, request):
        """VIN boýunça marka / model / ýyl (NHTSA vPIC açyk API)."""
        vin = (request.query_params.get('vin') or '').strip().upper()
        if len(vin) != 17:
            raise ValidationError({"vin": "VIN 17 simwol bolmaly."})
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{urllib.parse.quote(vin)}?format=json"
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            row = (data.get('Results') or [{}])[0]
        except Exception as exc:
            logger.warning("VIN decode failed: %s", exc)
            return Response({"detail": "VIN hyzmaty bilen baglanyşyk bolmady."}, status=status.HTTP_502_BAD_GATEWAY)

        make = (row.get('Make') or '').strip().title()
        model = (row.get('Model') or '').strip()
        year = _int(row.get('ModelYear'))
        if not make and not model:
            return Response({"detail": "Bu VIN boýunça maglumat tapylmady."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'vin': vin, 'make': make, 'model': model, 'year': year,
            'body_class': row.get('BodyClass') or '', 'engine': row.get('DisplacementL') or '',
            'fuel_type': row.get('FuelTypePrimary') or '',
        })

    # ---------------------------------------------------------------- Hasabatlar

    def _report_queryset(self, request):
        return apply_period_filter(self.get_queryset(), request.query_params)

    @action(detail=False, methods=['get'], url_path='reports/summary')
    def reports_summary(self, request):
        """
        Get aggregated report analytics & KPIs filtered by date / period.
        Ähli pul jemleri USD-da (her mukdar girizilen pursatdaky kurs boýunça öwrülýär).
        """
        vehicle_qs = self._report_queryset(request)

        total_vehicles = vehicle_qs.count()
        expenses_qs = VehicleExpense.objects.filter(vehicle__in=vehicle_qs)
        total_expenses_usd = expenses_qs.aggregate(total=Sum('amount_usd'))['total'] or 0
        expenses_by_currency = {
            r['currency']: _money(r['total'])
            for r in expenses_qs.values('currency').annotate(total=Sum('amount')).order_by('currency')
        }

        sold_qs = vehicle_qs.filter(status=VehicleStatus.SOLD, sale_price_usd__isnull=False)
        sold_agg = sold_qs.aggregate(sale=Sum('sale_price_usd'), purchase=Sum('purchase_price_usd'))
        sold_expenses = VehicleExpense.objects.filter(vehicle__in=sold_qs).aggregate(t=Sum('amount_usd'))['t'] or 0
        total_profit = (sold_agg['sale'] or 0) - (sold_agg['purchase'] or 0) - sold_expenses
        total_purchase = vehicle_qs.aggregate(t=Sum('purchase_price_usd'))['t'] or 0

        by_status = list(vehicle_qs.values('status').annotate(count=Count('vin')).order_by('-count'))
        by_location = list(vehicle_qs.values('location').annotate(count=Count('vin')).order_by('-count'))
        by_expense_title = [
            {**r, 'total_amount': _money(r['total_amount'])}
            for r in expenses_qs.values('title').annotate(total_amount=Sum('amount_usd'), count=Count('id')).order_by('-total_amount')
        ]
        by_expense_stage = [
            {**r, 'total_amount': _money(r['total_amount'])}
            for r in expenses_qs.values('stage').annotate(total_amount=Sum('amount_usd')).order_by('-total_amount')
        ]

        handed_over_count = vehicle_qs.filter(is_handed_over=True).count()
        assigned_count = vehicle_qs.filter(is_handed_over=False).count()

        vehicles_data = VehicleSerializer(vehicle_qs, many=True, context={'request': request}).data

        return Response({
            'kpis': {
                'total_vehicles': total_vehicles,
                'total_expenses_usd': _money(total_expenses_usd),
                'expenses_by_currency': expenses_by_currency,
                'handed_over_count': handed_over_count,
                'assigned_count': assigned_count,
                'sold_count': vehicle_qs.filter(status=VehicleStatus.SOLD).count(),
                'total_purchase_usd': _money(total_purchase),
                'total_sale_usd': _money(sold_agg['sale']),
                'total_profit_usd': _money(total_profit),
            },
            'by_status': by_status,
            'by_location': by_location,
            'by_expense_title': by_expense_title,
            'by_expense_stage': by_expense_stage,
            'vehicles': vehicles_data
        })

    EXPORT_COLUMNS = [
        ('VIN', lambda v: v.vin), ('Ady', lambda v: v.title), ('Marka', lambda v: v.make),
        ('Model', lambda v: v.model), ('Ýyly', lambda v: v.year), ('Reňki', lambda v: v.color),
        ('Status', lambda v: v.status), ('Ýeri', lambda v: v.location),
        ('Jogapkär', lambda v: user_label(v.current_owner)),
        ('Tabşyryldy', lambda v: 'Hawa' if v.is_handed_over else 'Ýok'),
        ('Lot', lambda v: v.lot_number), ('Konteýner', lambda v: v.container_number),
        ('ETA', lambda v: v.eta.isoformat() if v.eta else ''),
        ('Satyn alyş (USD)', lambda v: float(v.purchase_price_usd) if v.purchase_price_usd is not None else ''),
        ('Çykdajylar (USD)', lambda v: float(v.expenses.aggregate(t=Sum('amount_usd'))['t'] or 0)),
        ('Satuw (USD)', lambda v: float(v.sale_price_usd) if v.sale_price_usd is not None else ''),
        ('Girdeji (USD)', lambda v: float(v.sale_price_usd - (v.purchase_price_usd or 0) - (v.expenses.aggregate(t=Sum('amount_usd'))['t'] or 0)) if v.sale_price_usd is not None else ''),
        ('Satylan senesi', lambda v: timezone.localtime(v.sold_at).strftime('%Y-%m-%d') if v.sold_at else ''),
        ('Alyjy', lambda v: v.buyer_name), ('Alyjynyň telefony', lambda v: v.buyer_phone),
        ('Hasaba alnan', lambda v: timezone.localtime(v.created_at).strftime('%Y-%m-%d')),
    ]

    @action(detail=False, methods=['get'], url_path='reports/export')
    def reports_export(self, request):
        """Hasabaty Excel (xlsx) ýa-da CSV görnüşinde ýükläp almak. ?file_format=xlsx|csv"""
        vehicle_qs = self._report_queryset(request)
        headers = [c[0] for c in self.EXPORT_COLUMNS]
        rows = [[fn(v) for _, fn in self.EXPORT_COLUMNS] for v in vehicle_qs]
        stamp = timezone.localdate().isoformat()
        fmt = request.query_params.get('file_format', 'xlsx')

        if fmt == 'xlsx':
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font
            except ImportError:
                fmt = 'csv'
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = 'Awtoulaglar'
                ws.append(headers)
                for cell in ws[1]:
                    cell.font = Font(bold=True)
                for row in rows:
                    ws.append(row)
                for col in ws.columns:
                    width = max(len(str(c.value or '')) for c in col)
                    ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
                ws.freeze_panes = 'A2'
                buf = io.BytesIO()
                wb.save(buf)
                resp = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                resp['Content-Disposition'] = f'attachment; filename="copart-hasabat-{stamp}.xlsx"'
                return resp

        buf = io.StringIO()
        buf.write('﻿')  # Excel UTF-8 tanar ýaly
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        resp = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="copart-hasabat-{stamp}.csv"'
        return resp

    @action(detail=False, methods=['get'], url_path='reports/dashboard')
    def reports_dashboard(self, request):
        """Admin paneli: işgärler boýunça ýük, garaşylýan tabşyryşlar, gijikýän we ETA-sy geçen awtoulaglar."""
        if not request.user.is_admin_role:
            raise PermissionDenied("Diňe Admin üçin.")
        now = timezone.now()
        stale_days = getattr(settings, 'STALE_VEHICLE_DAYS', 30)
        active = Vehicle.objects.exclude(status=VehicleStatus.SOLD)

        employees = []
        for emp in User.objects.filter(role=User.Role.EMPLOYEE).order_by('first_name', 'last_name'):
            owned = Vehicle.objects.filter(current_owner=emp)
            employees.append({
                'id': emp.id, 'username': emp.username, 'first_name': emp.first_name, 'last_name': emp.last_name,
                'is_active': emp.is_active,
                'total': owned.count(),
                'active': owned.exclude(status=VehicleStatus.SOLD).count(),
                'handed_over': owned.filter(is_handed_over=True).count(),
                'pending_incoming': Vehicle.objects.filter(pending_handover_owner=emp).count(),
            })

        def brief(qs):
            return [{
                'vin': v.vin, 'title': v.title, 'status': v.status, 'location': v.location,
                'owner': user_label(v.current_owner), 'pending_owner': user_label(v.pending_handover_owner) if v.pending_handover_owner else None,
                'status_changed_at': v.status_changed_at, 'eta': v.eta,
            } for v in qs.select_related('current_owner', 'pending_handover_owner')[:50]]

        stale_qs = active.filter(Q(status_changed_at__lt=now - timedelta(days=stale_days)) |
                                 Q(status_changed_at__isnull=True, created_at__lt=now - timedelta(days=stale_days)))
        overdue_qs = active.filter(eta__lt=timezone.localdate()).exclude(status=VehicleStatus.ARRIVED_TKM)
        orphan_qs = Vehicle.objects.filter(Q(current_owner__isnull=True) | Q(current_owner__is_active=False))

        return Response({
            'stale_days': stale_days,
            'employees': employees,
            'pending_handovers': brief(Vehicle.objects.filter(pending_handover_owner__isnull=False)),
            'stale_vehicles': brief(stale_qs.order_by('status_changed_at')),
            'overdue_eta': brief(overdue_qs.order_by('eta')),
            'orphaned_vehicles': brief(orphan_qs),
            'counts': {
                'pending_handovers': Vehicle.objects.filter(pending_handover_owner__isnull=False).count(),
                'stale_vehicles': stale_qs.count(),
                'overdue_eta': overdue_qs.count(),
                'orphaned_vehicles': orphan_qs.count(),
            },
        })


# ---------------------------------------------------------------- Çykdajylar / resminamalar

class VehicleExpenseViewSet(viewsets.ModelViewSet):
    """
    Manage expenses for a specific vehicle by VIN.
    """
    serializer_class = VehicleExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_vehicle(self):
        vin = self.kwargs.get('vehicle_vin')
        vehicle = get_object_or_404(Vehicle, vin=vin)
        user = self.request.user
        if not can_read_vehicle_finance(vehicle, user):
            raise PermissionDenied("Siziň bu awtoulagyň çykdajylaryny görmäge hukugyňyz ýok.")
        return vehicle

    def get_queryset(self):
        vehicle = self.get_vehicle()
        return vehicle.expenses.select_related('created_by')

    def perform_create(self, serializer):
        vehicle = self.get_vehicle()
        check_vehicle_write_permission(vehicle, self.request.user)

        expense = add_vehicle_expense_service(
            vehicle=vehicle,
            title=serializer.validated_data['title'],
            amount=serializer.validated_data['amount'],
            currency=serializer.validated_data.get('currency', 'USD'),
            description=serializer.validated_data.get('description', ''),
            stage=serializer.validated_data.get('stage', ''),
            receipt=serializer.validated_data.get('receipt'),
            user=self.request.user
        )
        serializer.instance = expense

    def perform_update(self, serializer):
        instance = serializer.instance
        check_vehicle_write_permission(instance.vehicle, self.request.user)
        before = f"{instance.title} — {instance.amount} {instance.currency}"
        expense = serializer.save()
        after = f"{expense.title} — {expense.amount} {expense.currency}"
        log_event(expense.vehicle, Event.EXPENSE_UPDATED, f"Çykdajy üýtgedildi: {before} -> {after}", user=self.request.user)

    def perform_destroy(self, instance):
        # Pozmak hem ýazmak hukugyny talap edýär (goşmak bilen deň düzgün)
        check_vehicle_write_permission(instance.vehicle, self.request.user)
        vehicle = instance.vehicle
        note = f"Çykdajy pozuldy: {instance.title} — {instance.amount} {instance.currency}"
        instance.delete()
        log_event(vehicle, Event.EXPENSE_DELETED, note, user=self.request.user)


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
        if not can_read_vehicle_finance(vehicle, user):
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
            raise ValidationError({"file": "Faýl hökman gerek."})

        document = add_vehicle_document_service(
            vehicle=vehicle,
            file_obj=file_obj,
            title=serializer.validated_data['title'],
            document_type=serializer.validated_data.get('document_type', 'PHOTO'),
            user=self.request.user
        )
        serializer.instance = document

    def perform_destroy(self, instance):
        # Pozmak hem ýazmak hukugyny talap edýär (goşmak bilen deň düzgün)
        check_vehicle_write_permission(instance.vehicle, self.request.user)
        vehicle = instance.vehicle
        note = f"Resminama pozuldy: {instance.title} ({instance.document_type})"
        instance.delete()
        log_event(vehicle, Event.DOCUMENT_DELETED, note, user=self.request.user)


# ---------------------------------------------------------------- Bildirişler

class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Ulanyjynyň öz bildirişleri. ?unread=1 — diňe okalmadyklar."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get('unread') in ('1', 'true'):
            qs = qs.filter(is_read=False)
        return qs[:100]

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'count': Notification.objects.filter(user=request.user, is_read=False).count()})

    @action(detail=True, methods=['post'], url_path='read')
    def mark_read(self, request, pk=None):
        updated = Notification.objects.filter(user=request.user, pk=pk).update(is_read=True)
        if not updated:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({'ok': True})

    @action(detail=False, methods=['post'], url_path='read-all')
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})
