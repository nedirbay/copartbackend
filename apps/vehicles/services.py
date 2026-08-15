from django.db import transaction
from .models import Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument

@transaction.atomic
def create_vehicle_service(validated_data, created_by_user):
    """
    Creates a vehicle, assigns initial owner (or created_by_user),
    and logs the initial history log.
    """
    if 'current_owner' not in validated_data or validated_data['current_owner'] is None:
        validated_data['current_owner'] = created_by_user

    vehicle = Vehicle.objects.create(**validated_data)

    # Initial history log
    VehicleHistoryLog.objects.create(
        vehicle=vehicle,
        status=vehicle.status,
        location=vehicle.location,
        owner=vehicle.current_owner,
        changed_by=created_by_user,
        note="Vehicle initial registration"
    )

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

    log = VehicleHistoryLog.objects.create(
        vehicle=vehicle,
        status=vehicle.status,
        location=vehicle.location,
        owner=vehicle.current_owner,
        changed_by=user,
        note=note or f"Updated status to {vehicle.status}, location to {vehicle.location}"
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

    log = VehicleHistoryLog.objects.create(
        vehicle=vehicle,
        status=vehicle.status,
        location=vehicle.location,
        owner=new_owner_user,
        changed_by=user,
        note=note or f"Vehicle handed over to {new_owner_user.username}"
    )

    return vehicle, log

def add_vehicle_expense_service(vehicle, title, amount, currency="USD", description="", stage="", user=None):
    """
    Adds an expense for a vehicle.
    """
    expense = VehicleExpense.objects.create(
        vehicle=vehicle,
        title=title,
        amount=amount,
        currency=currency,
        description=description,
        stage=stage,
        created_by=user
    )
    return expense

def add_vehicle_document_service(vehicle, file_obj, title, document_type="PHOTO", user=None):
    """
    Uploads a photo or document for a vehicle.
    """
    document = VehicleDocument.objects.create(
        vehicle=vehicle,
        file=file_obj,
        title=title,
        document_type=document_type,
        uploaded_by=user
    )
    return document
