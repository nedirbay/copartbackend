"""Hukuk düzgünleriniň aýlanyp geçilmeýändigini barlaýan testler."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from vehicles.models import Vehicle, VehicleExpense, VehicleStatus, VehicleLocation

User = get_user_model()


@pytest.mark.django_db
class TestSecurityRules:

    def setup_method(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='adm', password='AdminPass123!', role=User.Role.ADMIN)
        self.emp1 = User.objects.create_user(username='emp1', password='Pass123!', role=User.Role.EMPLOYEE)
        self.emp2 = User.objects.create_user(username='emp2', password='Pass123!', role=User.Role.EMPLOYEE)
        self.vehicle = Vehicle.objects.create(
            vin='SECVIN0000000001', title='Test', make='Toyota', model='Camry', year=2022, color='Ak',
            status=VehicleStatus.PURCHASED, location=VehicleLocation.USA_COPART, current_owner=self.emp1,
        )
        self.url = f'/api/vehicles/{self.vehicle.vin}/'

    def _hand_over_to_emp2(self):
        self.vehicle.current_owner = self.emp2
        self.vehicle.is_handed_over = True
        self.vehicle.save()

    # --- Tabşyryş haýyşy ---

    def test_employee_cannot_hand_over_to_self(self):
        self.client.force_authenticate(self.emp1)
        res = self.client.post(self.url + 'handover/', {'employee_id': self.emp1.id})
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        self.vehicle.refresh_from_db()
        assert self.vehicle.pending_handover_owner is None

    def test_employee_cannot_hand_over_to_admin(self):
        self.client.force_authenticate(self.emp1)
        res = self.client.post(self.url + 'handover/', {'employee_id': self.admin.id})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_hand_over_to_inactive_employee(self):
        self.emp2.is_active = False
        self.emp2.save()
        self.client.force_authenticate(self.emp1)
        res = self.client.post(self.url + 'handover/', {'employee_id': self.emp2.id})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_pending_owner_cannot_be_set_via_update(self):
        self._hand_over_to_emp2()
        self.client.force_authenticate(self.emp2)
        res = self.client.patch(self.url, {'pending_handover_owner': self.emp1.id}, format='json')
        assert res.status_code == status.HTTP_200_OK
        self.vehicle.refresh_from_db()
        assert self.vehicle.pending_handover_owner is None

    # --- PUT/PATCH arkaly aýlanyp geçmek ---

    def test_admin_cannot_edit_handed_over_vehicle(self):
        self._hand_over_to_emp2()
        self.client.force_authenticate(self.admin)
        res = self.client.patch(self.url, {'status': VehicleStatus.SOLD}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN
        self.vehicle.refresh_from_db()
        assert self.vehicle.status == VehicleStatus.PURCHASED

    def test_admin_cannot_reassign_handed_over_vehicle_via_update(self):
        self._hand_over_to_emp2()
        self.client.force_authenticate(self.admin)
        res = self.client.patch(self.url, {'current_owner': self.emp1.id}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN
        self.vehicle.refresh_from_db()
        assert self.vehicle.current_owner == self.emp2

    def test_owner_employee_cannot_change_owner_via_update(self):
        self._hand_over_to_emp2()
        self.client.force_authenticate(self.emp2)
        res = self.client.patch(self.url, {'current_owner': self.emp1.id}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_employee_can_edit_handed_over_vehicle(self):
        self._hand_over_to_emp2()
        self.client.force_authenticate(self.emp2)
        res = self.client.patch(self.url, {'mileage': 123}, format='json')
        assert res.status_code == status.HTTP_200_OK

    def test_admin_can_change_owner_before_handover(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(self.url, {'current_owner': self.emp2.id}, format='json')
        assert res.status_code == status.HTTP_200_OK
        self.vehicle.refresh_from_db()
        assert self.vehicle.current_owner == self.emp2

    # --- Çykdajy pozmak ---

    def test_assigned_employee_cannot_delete_expense(self):
        exp = VehicleExpense.objects.create(vehicle=self.vehicle, title='Auksion', amount=100)
        self.client.force_authenticate(self.emp1)
        res = self.client.delete(f'{self.url}expenses/{exp.id}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert VehicleExpense.objects.filter(id=exp.id).exists()

    def test_admin_can_delete_expense_before_handover(self):
        exp = VehicleExpense.objects.create(vehicle=self.vehicle, title='Auksion', amount=100)
        self.client.force_authenticate(self.admin)
        res = self.client.delete(f'{self.url}expenses/{exp.id}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT

    def test_pending_owner_can_read_expenses(self):
        self.vehicle.pending_handover_owner = self.emp2
        self.vehicle.save()
        self.client.force_authenticate(self.emp2)
        res = self.client.get(f'{self.url}expenses/')
        assert res.status_code == status.HTTP_200_OK

    def test_document_upload_without_file_is_400(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(f'{self.url}documents/', {'title': 'x', 'document_type': 'OTHER'})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    # --- Açyk parollar ---

    def test_raw_password_not_leaked_in_vehicle_or_profile(self):
        self.client.force_authenticate(self.emp1)
        vehicle_res = self.client.get(self.url)
        assert 'raw_password' not in vehicle_res.data['current_owner_detail']
        history_res = self.client.get(self.url + 'history/')
        assert all('raw_password' not in (log.get('owner_detail') or {}) for log in history_res.data)
        me_res = self.client.get('/api/auth/me/')
        assert 'raw_password' not in me_res.data

    def test_passwords_never_returned_in_employee_list(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get('/api/auth/employees/')
        rows = res.data['results'] if isinstance(res.data, dict) else res.data
        assert rows and all('raw_password' not in r for r in rows)
