import pytest
import io
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from vehicles.models import Vehicle, VehicleStatus, VehicleLocation

User = get_user_model()

@pytest.mark.django_db
class TestHandoverAndExpenses:

    def setup_method(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username='admin_copart',
            password='AdminPassword123!',
            role=User.Role.ADMIN
        )
        self.emp = User.objects.create_user(
            username='emp_gruziya',
            password='Password123!',
            role=User.Role.EMPLOYEE
        )
        self.vehicle = Vehicle.objects.create(
            vin='VINHANDOVER12345',
            title='Hyundai Elantra',
            make='Hyundai',
            model='Elantra',
            year=2023,
            color='Grey',
            status=VehicleStatus.IN_TRANSIT,
            location=VehicleLocation.GEORGIA,
            current_owner=self.admin_user
        )

    def test_handover_to_employee(self):
        # 1. Admin assigns vehicle to emp
        self.client.force_authenticate(user=self.admin_user)
        assign_res = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/assign/',
            {
                'employee_id': self.emp.id,
                'note': 'Assigned to emp_gruziya'
            }
        )
        assert assign_res.status_code == status.HTTP_200_OK
        self.vehicle.refresh_from_db()
        assert self.vehicle.current_owner == self.emp

        # 2. emp initiates handover to emp2
        emp2 = User.objects.create_user(username='emp_tkm', password='Password123!', role=User.Role.EMPLOYEE)
        self.client.force_authenticate(user=self.emp)
        handover_res = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/handover/',
            {
                'employee_id': emp2.id,
                'note': 'Handover request for emp_tkm'
            }
        )
        assert handover_res.status_code == status.HTTP_200_OK

        # 3. emp2 confirms handover
        self.client.force_authenticate(user=emp2)
        confirm_res = self.client.post(f'/api/vehicles/{self.vehicle.vin}/confirm-handover/')
        assert confirm_res.status_code == status.HTTP_200_OK
        
        self.vehicle.refresh_from_db()
        assert self.vehicle.current_owner == emp2
        assert self.vehicle.is_handed_over is True

        # emp2 can now update vehicle status
        update_res = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/update-status-location/',
            {
                'status': VehicleStatus.ARRIVED_TKM,
                'location': VehicleLocation.TURKMENISTAN_INTERNAL,
                'note': 'Arrived at Ashgabat customs'
            }
        )
        assert update_res.status_code == status.HTTP_200_OK
        assert update_res.data['vehicle']['status'] == VehicleStatus.ARRIVED_TKM


    def test_expenses_tracking(self):
        self.client.force_authenticate(user=self.admin_user)
        # Add expense 1
        res1 = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/expenses/',
            {
                'title': 'Auction Fee Copart',
                'amount': '650.00',
                'currency': 'USD',
                'description': 'Standard buyer fee',
                'stage': 'USA'
            }
        )
        assert res1.status_code == status.HTTP_201_CREATED

        # Add expense 2
        res2 = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/expenses/',
            {
                'title': 'Ocean Freight Shipping',
                'amount': '1800.00',
                'currency': 'USD',
                'stage': 'Shipping'
            }
        )
        assert res2.status_code == status.HTTP_201_CREATED

        # Check total expenses on vehicle details
        veh_res = self.client.get(f'/api/vehicles/{self.vehicle.vin}/')
        assert veh_res.status_code == status.HTTP_200_OK
        assert veh_res.data['total_expenses'] == '2450.00'

    def test_document_photo_upload(self):
        self.client.force_authenticate(user=self.admin_user)
        dummy_file = SimpleUploadedFile("car_front.jpg", b"fake_image_bytes", content_type="image/jpeg")
        
        res = self.client.post(
            f'/api/vehicles/{self.vehicle.vin}/documents/',
            {
                'title': 'Front view photo',
                'document_type': 'PHOTO',
                'file': dummy_file
            },
            format='multipart'
        )
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['title'] == 'Front view photo'
        assert self.vehicle.documents.count() == 1
