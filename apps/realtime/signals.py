"""
Model signallary -> real-time wakalar.

Awtoulag wakasy diňe ony görmäge hukugy bolanlara gidýär: Adminler, jogapkär işgär,
kabul etmäge garaşýan işgär we (awtoulag başga birine geçen bolsa) öňki jogapkär / garaşýan —
olar hem sanawyny täzeläp, awtoulagy aýyrmaly.
"""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_init, post_save
from django.dispatch import receiver

from vehicles.models import (
    Currency, DynamicVehicleLocation, DynamicVehicleStatus, ExpenseType, Make, Vehicle,
    VehicleDocument, VehicleExpense, VehicleHistoryLog, VehicleModel,
)

from .events import (
    ADMIN_GROUP, ALL_GROUP, DICTIONARY_CHANGED, EMPLOYEES_CHANGED, VEHICLE_CHANGED, VEHICLE_DELETED,
    force_logout, publish, user_group,
)

User = get_user_model()

_OWNER_FIELDS = ('current_owner_id', 'pending_handover_owner_id')


def _vehicle_groups(*user_ids):
    return {ADMIN_GROUP, *(user_group(uid) for uid in user_ids if uid)}


# ---------------------------------------------------------------- Awtoulag

@receiver(post_init, sender=Vehicle)
def _remember_vehicle_audience(sender, instance, **kwargs):
    # __dict__ — goýbolsun edilen (deferred) meýdanlar üçin goşmaça sorag etmezlik üçin
    instance._rt_prev_users = {instance.__dict__.get(f) for f in _OWNER_FIELDS}


def _current_users(vehicle):
    return {getattr(vehicle, f) for f in _OWNER_FIELDS}


@receiver(post_save, sender=Vehicle)
def _vehicle_saved(sender, instance, **kwargs):
    users = _current_users(instance) | getattr(instance, '_rt_prev_users', set())
    publish(_vehicle_groups(*users), VEHICLE_CHANGED, vin=instance.vin)
    instance._rt_prev_users = _current_users(instance)


@receiver(post_delete, sender=Vehicle)
def _vehicle_deleted(sender, instance, **kwargs):
    users = _current_users(instance) | getattr(instance, '_rt_prev_users', set())
    publish(_vehicle_groups(*users), VEHICLE_DELETED, vin=instance.vin)


def _vehicle_child_changed(sender, instance, **kwargs):
    """Çykdajy / resminama / taryh üýtgände — degişli awtoulag üýtgedi hasaplanýar."""
    owners = Vehicle.objects.filter(pk=instance.vehicle_id).values_list(*_OWNER_FIELDS).first()
    if owners is None:  # awtoulag bilen bile pozulýar — vehicle.deleted eýýäm ugradylýar
        return
    publish(_vehicle_groups(*owners), VEHICLE_CHANGED, vin=instance.vehicle_id)


for _model in (VehicleExpense, VehicleDocument, VehicleHistoryLog):
    post_save.connect(_vehicle_child_changed, sender=_model, dispatch_uid=f'rt-save-{_model.__name__}')
    post_delete.connect(_vehicle_child_changed, sender=_model, dispatch_uid=f'rt-delete-{_model.__name__}')


# ---------------------------------------------------------------- Sözlükler

DICTIONARY_NAMES = {
    DynamicVehicleStatus: 'statuses',
    DynamicVehicleLocation: 'locations',
    Make: 'makes',
    VehicleModel: 'models',
    Currency: 'currencies',
    ExpenseType: 'expense_types',
}


def _dictionary_changed(sender, instance, **kwargs):
    publish([ALL_GROUP], DICTIONARY_CHANGED, name=DICTIONARY_NAMES[sender])


for _model in DICTIONARY_NAMES:
    post_save.connect(_dictionary_changed, sender=_model, dispatch_uid=f'rt-save-{_model.__name__}')
    post_delete.connect(_dictionary_changed, sender=_model, dispatch_uid=f'rt-delete-{_model.__name__}')


# ---------------------------------------------------------------- Ulanyjylar

@receiver(post_save, sender=User)
def _user_saved(sender, instance, update_fields=None, **kwargs):
    if update_fields and set(update_fields) <= {'last_login'}:
        return  # her giriş üçin Adminlere signal ugratmaly däl
    if instance.role == User.Role.EMPLOYEE:
        publish([ADMIN_GROUP], EMPLOYEES_CHANGED)
    if not instance.is_active:
        force_logout(instance.pk)


@receiver(post_delete, sender=User)
def _user_deleted(sender, instance, **kwargs):
    publish([ADMIN_GROUP], EMPLOYEES_CHANGED)
    force_logout(instance.pk)
