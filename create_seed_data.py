import os
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apps'))

import django
django.setup()

from django.contrib.auth import get_user_model
from vehicles.models import Vehicle, VehicleStatus, VehicleLocation, VehicleHistoryLog, VehicleExpense

User = get_user_model()

def create_seed():
    print("Creating seed data...")

    # 1. Create Admin User
    admin, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'first_name': 'Admin',
            'last_name': 'Copart',
            'email': 'admin@copart.com',
            'role': User.Role.ADMIN,
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created or not admin.check_password('adminpassword123'):
        admin.set_password('adminpassword123')
        admin.save()
        print("Created/Updated Admin user: admin / adminpassword123")

    # 2. Create Employee User
    employee, emp_created = User.objects.get_or_create(
        username='isgar_merdan',
        defaults={
            'first_name': 'Merdan',
            'last_name': 'Annamyradow',
            'email': 'merdan@copart.com',
            'phone_number': '+99365123456',
            'role': User.Role.EMPLOYEE
        }
    )
    if emp_created or not employee.check_password('employeepassword123'):
        employee.set_password('employeepassword123')
        employee.save()
        print("Created/Updated Employee user: isgar_merdan / employeepassword123")

    # 3. Create Sample Vehicle 1
    v1, v1_created = Vehicle.objects.get_or_create(
        vin='1HGCR2F83HA123456',
        defaults={
            'title': 'Toyota Camry 2022 SE',
            'make': 'Toyota',
            'model': 'Camry',
            'year': 2022,
            'color': 'Gara',
            'mileage': 15400,
            'status': VehicleStatus.PURCHASED,
            'location': VehicleLocation.USA_COPART,
            'current_owner': admin
        }
    )
    if v1_created:
        VehicleHistoryLog.objects.create(
            vehicle=v1,
            status=v1.status,
            location=v1.location,
            owner=admin,
            changed_by=admin,
            note="Copart auksionyndan satyn alyndy"
        )
        VehicleExpense.objects.create(
            vehicle=v1,
            title="Copart Auksion tölegi",
            amount=680.00,
            currency="USD",
            stage="Copart",
            created_by=admin
        )
        print("Created sample vehicle 1: 1HGCR2F83HA123456")

    # 4. Create Sample Vehicle 2 (Assigned to Employee)
    v2, v2_created = Vehicle.objects.get_or_create(
        vin='5YJ3E1EA7KF654321',
        defaults={
            'title': 'Tesla Model 3 2021',
            'make': 'Tesla',
            'model': 'Model 3',
            'year': 2021,
            'color': 'Ak',
            'mileage': 28000,
            'status': VehicleStatus.ARRIVED_TKM,
            'location': VehicleLocation.TURKMENISTAN_INTERNAL,
            'current_owner': employee,
            'is_handed_over': True
        }
    )
    if v2_created:
        VehicleHistoryLog.objects.create(
            vehicle=v2,
            status=v2.status,
            location=v2.location,
            owner=employee,
            changed_by=admin,
            note="Awtoulag Gruziýada Merdana tabşyryldy we Türkmenistana geldi"
        )
        VehicleExpense.objects.create(
            vehicle=v2,
            title="Konteýner Ýük daşama tölegi",
            amount=2100.00,
            currency="USD",
            stage="Shipping",
            created_by=admin
        )
        print("Created sample vehicle 2: 5YJ3E1EA7KF654321")

    print("Seed data creation finished successfully!")

if __name__ == '__main__':
    create_seed()
