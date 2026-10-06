import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from vehicles.models import Vehicle, VehicleStatus, VehicleLocation, VehicleHistoryLog

User = get_user_model()

@pytest.mark.django_db
class TestVehicles:

    def setup_method(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username='admin_copart',
            password='AdminPassword123!',
            role=User.Role.ADMIN
        )
        self.emp1 = User.objects.create_user(
            username='emp_merdan',
            password='Password123!',
            role=User.Role.EMPLOYEE
        )
        self.emp2 = User.objects.create_user(
            username='emp_durdy',
            password='Password123!',
            role=User.Role.EMPLOYEE
        )

    def test_admin_create_vehicle(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'vin': '14982374982749812',
            'title': 'Toyota Camry 2022 SE',
            'make': 'Toyota',
            'model': 'Camry',
            'year': 2022,
            'color': 'Black',
            'mileage': 15000,
            'status': VehicleStatus.PURCHASED,
            'location': VehicleLocation.USA_COPART
        }
        response = self.client.post('/api/vehicles/', payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['vin'] == '14982374982749812'
        
        # Verify initial history log was created
        vehicle = Vehicle.objects.get(vin='14982374982749812')
        assert vehicle.history_logs.count() == 1
        log = vehicle.history_logs.first()
        assert log.status == VehicleStatus.PURCHASED
        assert log.location == VehicleLocation.USA_COPART

    def test_employee_cannot_create_vehicle(self):
        self.client.force_authenticate(user=self.emp1)
        payload = {
            'vin': '99982374982749812',
            'title': 'BMW X5',
            'make': 'BMW',
            'model': 'X5',
            'year': 2021,
            'color': 'White',
            'mileage': 30000
        }
        response = self.client.post('/api/vehicles/', payload)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_vehicle_list_visibility(self):
        # Create vehicle assigned to emp1 and another unassigned
        v1 = Vehicle.objects.create(
            vin='VIN11111111111111',
            title='Ford Mustang',
            make='Ford',
            model='Mustang',
            year=2020,
            color='Red',
            current_owner=self.emp1
        )
        v2 = Vehicle.objects.create(
            vin='VIN22222222222222',
            title='Lexus RX350',
            make='Lexus',
            model='RX350',
            year=2021,
            color='Silver',
            current_owner=self.emp2
        )

        # Admin sees both vehicles
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get('/api/vehicles/')
        assert res_admin.status_code == status.HTTP_200_OK
        assert len(res_admin.data['results'] if 'results' in res_admin.data else res_admin.data) == 2

        # emp1 sees only v1
        self.client.force_authenticate(user=self.emp1)
        res_emp1 = self.client.get('/api/vehicles/')
        assert res_emp1.status_code == status.HTTP_200_OK
        vehicles_list = res_emp1.data['results'] if 'results' in res_emp1.data else res_emp1.data
        assert len(vehicles_list) == 1
        assert vehicles_list[0]['vin'] == 'VIN11111111111111'

    def test_update_status_and_location(self):
        v = Vehicle.objects.create(
            vin='VIN33333333333333',
            title='Toyota Corolla',
            make='Toyota',
            model='Corolla',
            year=2022,
            color='Blue',
            status=VehicleStatus.PURCHASED,
            location=VehicleLocation.USA_COPART,
            current_owner=self.admin_user
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f'/api/vehicles/{v.vin}/update-status-location/',
            {
                'status': VehicleStatus.IN_TRANSIT,
                'location': VehicleLocation.SHIPPING_TRANSIT,
                'note': 'Shipped on container #123'
            }
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['vehicle']['status'] == VehicleStatus.IN_TRANSIT
        assert response.data['vehicle']['location'] == VehicleLocation.SHIPPING_TRANSIT

        # Verify history logs endpoint
        hist_res = self.client.get(f'/api/vehicles/{v.vin}/history/')
        assert hist_res.status_code == status.HTTP_200_OK
        assert len(hist_res.data) == 1
        assert hist_res.data[0]['note'] == 'Shipped on container #123'

    def test_admin_update_vehicle(self):
        v = Vehicle.objects.create(
            vin='VINEDIT1111111111',
            title='Old Title',
            make='Toyota',
            model='Camry',
            year=2020,
            color='White',
            mileage=5000,
            current_owner=self.admin_user
        )
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            f'/api/vehicles/{v.vin}/',
            {'title': 'Updated Title', 'color': 'Black', 'mileage': 6200}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == 'Updated Title'
        assert response.data['color'] == 'Black'
        assert response.data['mileage'] == 6200

    def test_admin_delete_vehicle(self):
        v = Vehicle.objects.create(
            vin='VINDELETE1111111',
            title='To Delete',
            make='Toyota',
            model='Corolla',
            year=2019,
            color='Silver',
            current_owner=self.admin_user
        )
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.delete(f'/api/vehicles/{v.vin}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT
        assert not Vehicle.objects.filter(vin='VINDELETE1111111').exists()

    def test_employee_cannot_delete_vehicle(self):
        v = Vehicle.objects.create(
            vin='VINDELETE2222222',
            title='To Delete By Employee',
            make='Toyota',
            model='Corolla',
            year=2019,
            color='Silver',
            current_owner=self.emp1
        )
        self.client.force_authenticate(user=self.emp1)
        res = self.client.delete(f'/api/vehicles/{v.vin}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN
