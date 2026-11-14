from django.db import transaction
from .models import Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument, Make, VehicleModel

Event = VehicleHistoryLog.Event


def log_event(vehicle, event, note, user=None, owner=None):
    """Awtoulag taryhyna ýazgy goşýar (häzirki status, ýer we jogapkär bilen)."""
    return VehicleHistoryLog.objects.create(
        vehicle=vehicle,
        event=event,
        status=vehicle.status,
        location=vehicle.location,
        owner=owner if owner is not None else vehicle.current_owner,
        changed_by=user,
        note=note,
    )


def sync_make_model(make_name, model_name):
    """Marka / model sözlükde ýok bolsa goşulýar — sözlük hakyky ulanylýan maglumat bilen gabat gelýär."""
    make_name = (make_name or '').strip()
    model_name = (model_name or '').strip()
    if not make_name:
        return
    make = Make.objects.filter(name__iexact=make_name).first() or Make.objects.create(name=make_name)
    if model_name and not VehicleModel.objects.filter(make=make, name__iexact=model_name).exists():
        VehicleModel.objects.create(make=make, name=model_name)


@transaction.atomic
def create_vehicle_service(validated_data, created_by_user):
    """
    Creates a vehicle, assigns initial owner (or created_by_user),
    and logs the initial history log.
    """
    if 'current_owner' not in validated_data or validated_data['current_owner'] is None:
        validated_data['current_owner'] = created_by_user

    vehicle = Vehicle.objects.create(**validated_data)
    sync_make_model(vehicle.make, vehicle.model)
    log_event(vehicle, Event.CREATED, "Vehicle initial registration", user=created_by_user)
    return vehicle


@transaction.atomic
def update_vehicle_status_location_service(vehicle, status=None, location=None, note="", user=None):
    """
    Updates vehicle status and/or location, and creates a history log entry.
    """
    if status:
        vehicle.status = status
    if location:
        vehicle.location = location

    vehicle.save()

    log = log_event(
        vehicle, Event.STATUS,
        note or f"Updated status to {vehicle.status}, location to {vehicle.location}",
        user=user,
    )
    return vehicle, log


@transaction.atomic
def handover_vehicle_service(vehicle, new_owner_user, note="", user=None):
    """
    Kabul ediş-tabşyryş: Handover vehicle responsibility to specified employee user.
    """
    vehicle.current_owner = new_owner_user
    vehicle.is_handed_over = True
    vehicle.save()

    log = log_event(
        vehicle, Event.HANDOVER_CONFIRMED,
        note or f"Vehicle handed over to {new_owner_user.username}",
        user=user, owner=new_owner_user,
    )
    return vehicle, log


@transaction.atomic
def add_vehicle_expense_service(vehicle, title, amount, currency="USD", description="", stage="", user=None, receipt=None):
    """
    Adds an expense for a vehicle and records it in history.
    """
    expense = VehicleExpense.objects.create(
        vehicle=vehicle,
        title=title,
        amount=amount,
        currency=currency,
        description=description,
        stage=stage,
        receipt=receipt,
        created_by=user
    )
    log_event(vehicle, Event.EXPENSE_ADDED, f"Çykdajy goşuldy: {title} — {amount} {currency}", user=user)
    return expense


@transaction.atomic
def add_vehicle_document_service(vehicle, file_obj, title, document_type="PHOTO", user=None):
    """
    Uploads a photo or document for a vehicle and records it in history.
    """
    document = VehicleDocument.objects.create(
        vehicle=vehicle,
        file=file_obj,
        title=title,
        document_type=document_type,
        uploaded_by=user
    )
    log_event(vehicle, Event.DOCUMENT_ADDED, f"Resminama goşuldy: {title} ({document_type})", user=user)
    return document
