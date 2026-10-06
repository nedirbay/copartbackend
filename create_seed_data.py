import os
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apps'))

import django
django.setup()

from django.contrib.auth import get_user_model
from vehicles.models import (
    Vehicle, VehicleStatus, VehicleLocation, VehicleHistoryLog, VehicleExpense,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType
)

User = get_user_model()

def create_seed():
    print("=" * 60)
    print("  COPART ERP - BAŞLANGYÇ MAGLUMATLARY ÝÜKLEMEK SCRIPT-I")
    print("=" * 60)

    # 1. Dictionaries Seed
    print("\n[1/4] Sözlükler döredilýär...")
    statuses = [
        ('PURCHASED', 'Satyn alyndy'),
        ('IN_TRANSIT', 'Ýolda'),
        ('ARRIVED_TKM', 'Türkmenistana geldi'),
        ('SOLD', 'Satyldy'),
    ]
    for code, name in statuses:
        DynamicVehicleStatus.objects.get_or_create(code=code, defaults={'name': name})

    locations = [
        ('USA_COPART', 'Amerika (Copart)'),
        ('SHIPPING_TRANSIT', 'Ýük daşama ýola çykaryldy'),
        ('GEORGIA', 'Gruziýa'),
        ('TURKMENISTAN_INTERNAL', 'Türkmenistan (Içerki ýerleri)'),
    ]
    for code, name in locations:
        DynamicVehicleLocation.objects.get_or_create(code=code, defaults={'name': name})

    currencies = [
        ('USD', 'Dollar ($)', '$'),
        ('TMT', 'Manat (m.)', 'm.'),
        ('EUR', 'Euro (€)', '€'),
    ]
    for code, name, symbol in currencies:
        Currency.objects.get_or_create(code=code, defaults={'name': name, 'symbol': symbol})

    expense_types = [
        'Copart Auksion tölegi',
        'Konteýner / Ýük daşama tölegi (Shipping)',
        'Gruziýa awtovoz / port tölegi',
        'Serhet / Gözgörme tölegi',
        'Gümrük (Rastamožka) tölegi',
        'Ussa we Bejergi tölegi',
        'Resminama / Ätiýaçlandyryş tölegi',
        'Ýangyç tölegi',
        'Başga çykdajy',
    ]
    for exp_name in expense_types:
        ExpenseType.objects.get_or_create(name=exp_name)

    makes_and_models = {
        'Toyota': ['Camry', 'Corolla', 'RAV4', 'Highlander', 'Land Cruiser', 'Avalon', 'Prius'],
        'Lexus': ['RX350', 'ES350', 'GX460', 'LX570', 'LX600', 'NX200', 'IS250'],
        'BMW': ['X5', 'X6', 'X7', '3 Series', '5 Series', '7 Series', 'M5'],
        'Mercedes-Benz': ['C-Class', 'E-Class', 'S-Class', 'GLE', 'GLS', 'G-Class', 'CLA'],
        'Ford': ['Fusion', 'Escape', 'F-150', 'Mustang', 'Explorer', 'Focus'],
        'Hyundai': ['Elantra', 'Sonata', 'Tucson', 'Santa Fe', 'Genesis', 'Palisade'],
        'Kia': ['Optima', 'K5', 'Sportage', 'Sorento', 'Carnival', 'Stinger'],
        'Tesla': ['Model 3', 'Model Y', 'Model S', 'Model X', 'Cybertruck'],
        'Nissan': ['Rogue', 'Altima', 'Sentra', 'Murano', 'Patrol'],
        'Chevrolet': ['Malibu', 'Cruze', 'Equinox', 'Tahoe', 'Suburban', 'Camaro'],
        'Honda': ['Accord', 'Civic', 'CR-V', 'Pilot'],
        'Audi': ['A4', 'A6', 'Q5', 'Q7', 'Q8'],
        'Volkswagen': ['Jetta', 'Passat', 'Tiguan', 'Touareg', 'Golf'],
    }
    for make_name, models_list in makes_and_models.items():
        make_obj, _ = Make.objects.get_or_create(name=make_name)
        for model_name in models_list:
            VehicleModel.objects.get_or_create(make=make_obj, name=model_name)

    print("  -> Statuslar, ýerleşýän ýerler, pul birlikleri, çykdajylar we markalar döredildi.")

    # 2. Users Seed
    print("\n[2/4] Ulanyjylar döredilýär...")
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
    print("  -> Admin: username='admin' | password='adminpassword123'")

    employee1, emp1_created = User.objects.get_or_create(
        username='isgar_merdan',
        defaults={
            'first_name': 'Merdan',
            'last_name': 'Annamyradow',
            'email': 'merdan@copart.com',
            'phone_number': '+99365123456',
            'role': User.Role.EMPLOYEE
        }
    )
    if emp1_created or not employee1.check_password('employeepassword123'):
        employee1.set_password('employeepassword123')
        employee1.raw_password = 'employeepassword123'
        employee1.save()
    print("  -> Işgär 1: username='isgar_merdan' | password='employeepassword123'")

    employee2, emp2_created = User.objects.get_or_create(
        username='isgar_durdy',
        defaults={
            'first_name': 'Durdy',
            'last_name': 'Gurbanow',
            'email': 'durdy@copart.com',
            'phone_number': '+99365654321',
            'role': User.Role.EMPLOYEE
        }
    )
    if emp2_created or not employee2.check_password('employeepassword123'):
        employee2.set_password('employeepassword123')
        employee2.raw_password = 'employeepassword123'
        employee2.save()
    print("  -> Işgär 2: username='isgar_durdy' | password='employeepassword123'")

    # 3. Sample Vehicles Seed
    print("\n[3/4] Synag awtoulaglary we çykdajylary döredilýär...")

    # Vehicle 1: Toyota Camry 2022
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

    # Vehicle 2: Tesla Model 3 2021
    v2, v2_created = Vehicle.objects.get_or_create(
        vin='5YJ3E1EA7KF654321',
        defaults={
            'title': 'Tesla Model 3 2021 Long Range',
            'make': 'Tesla',
            'model': 'Model 3',
            'year': 2021,
            'color': 'Ak',
            'mileage': 28000,
            'status': VehicleStatus.ARRIVED_TKM,
            'location': VehicleLocation.TURKMENISTAN_INTERNAL,
            'current_owner': employee1,
            'is_handed_over': True
        }
    )
    if v2_created:
        VehicleHistoryLog.objects.create(
            vehicle=v2,
            status=v2.status,
            location=v2.location,
            owner=employee1,
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
        VehicleExpense.objects.create(
            vehicle=v2,
            title="Serhet / Gözgörme tölegi",
            amount=350.00,
            currency="USD",
            stage="Customs",
            created_by=employee1
        )

    # Vehicle 3: Lexus RX350 2020
    v3, v3_created = Vehicle.objects.get_or_create(
        vin='4T1B11HK5JU889900',
        defaults={
            'title': 'Lexus RX350 2020 F-Sport',
            'make': 'Lexus',
            'model': 'RX350',
            'year': 2020,
            'color': 'Çal / Kümüş',
            'mileage': 32000,
            'status': VehicleStatus.IN_TRANSIT,
            'location': VehicleLocation.SHIPPING_TRANSIT,
            'current_owner': employee2,
            'is_handed_over': False
        }
    )
    if v3_created:
        VehicleHistoryLog.objects.create(
            vehicle=v3,
            status=v3.status,
            location=v3.location,
            owner=employee2,
            changed_by=admin,
            note="Awtoulag Poti portyna ugradyldy (Shipping)"
        )
        VehicleExpense.objects.create(
            vehicle=v3,
            title="Konteýner / Ýük daşama tölegi (Shipping)",
            amount=1950.00,
            currency="USD",
            stage="Shipping",
            created_by=admin
        )

    # Vehicle 4: BMW X5 2021
    v4, v4_created = Vehicle.objects.get_or_create(
        vin='WBA3A5C58DF112233',
        defaults={
            'title': 'BMW X5 2021 xDrive40i',
            'make': 'BMW',
            'model': 'X5',
            'year': 2021,
            'color': 'Gara',
            'mileage': 41000,
            'status': VehicleStatus.SOLD,
            'location': VehicleLocation.TURKMENISTAN_INTERNAL,
            'current_owner': employee1,
            'is_handed_over': True
        }
    )
    if v4_created:
        VehicleHistoryLog.objects.create(
            vehicle=v4,
            status=v4.status,
            location=v4.location,
            owner=employee1,
            changed_by=employee1,
            note="Awtoulag Türkmenistanda müşderä satyldy"
        )
        VehicleExpense.objects.create(
            vehicle=v4,
            title="Ussa we Bejergi tölegi",
            amount=420.00,
            currency="USD",
            stage="Repair",
            created_by=employee1
        )

    print("  -> 4 sany synag awtoulagy (Toyota, Tesla, Lexus, BMW) we çykdajylary döredildi.")

    print("\n[4/4] Taýýar!")
    print("=" * 60)
    print("  ULANYJY MAGLUMATLARY (GIRIŞ ÜÇIN):")
    print("  - Admin:       admin         | adminpassword123")
    print("  - Işgär 1:     isgar_merdan  | employeepassword123")
    print("  - Işgär 2:     isgar_durdy   | employeepassword123")
    print("=" * 60)

if __name__ == '__main__':
    create_seed()
