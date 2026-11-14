"""Täze logika: sözlük baglanyşygy, walýuta, girdeji, tabşyryş ret/ýatyrma, admin mejbury hereketleri, audit, hasabatlar."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vehicles.models import (
    Vehicle, VehicleExpense, VehicleHistoryLog, Notification, Currency,
    DynamicVehicleStatus, Make, VehicleModel,
)

User = get_user_model()
Event = VehicleHistoryLog.Event


@pytest.mark.django_db
class TestFeatures:

    def setup_method(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='adm', password='AdminPass123!', role=User.Role.ADMIN)
        self.emp1 = User.objects.create_user(username='emp1', password='Pass123!x', role=User.Role.EMPLOYEE)
        self.emp2 = User.objects.create_user(username='emp2', password='Pass123!x', role=User.Role.EMPLOYEE)
        Currency.objects.filter(code='TMT').update(usd_rate=Decimal('3.5'))
        self.vehicle = Vehicle.objects.create(
            vin='FEATVIN000000001', title='T', make='Toyota', model='Camry', year=2022, color='Ak',
            current_owner=self.emp1,
        )
        self.url = f'/api/vehicles/{self.vehicle.vin}/'

    def _handed_over(self, owner):
        self.vehicle.refresh_from_db()
        self.vehicle.current_owner = owner
        self.vehicle.is_handed_over = True
        self.vehicle.save()

    # --- Sözlükler ---

    def test_unknown_status_rejected_and_new_dictionary_status_accepted(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(self.url, {'status': 'AT_CUSTOMS'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        DynamicVehicleStatus.objects.create(code='AT_CUSTOMS', name='Gümrükde')
        res = self.client.patch(self.url, {'status': 'AT_CUSTOMS'}, format='json')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['status'] == 'AT_CUSTOMS'

    def test_used_or_system_status_cannot_be_deleted(self):
        self.client.force_authenticate(self.admin)
        sold = DynamicVehicleStatus.objects.get(code='SOLD')
        assert self.client.delete(f'/api/vehicles/dictionaries/statuses/{sold.id}/').status_code == 400
        custom = DynamicVehicleStatus.objects.create(code='AT_CUSTOMS', name='Gümrükde')
        self.vehicle.status = 'AT_CUSTOMS'
        self.vehicle.save()
        assert self.client.delete(f'/api/vehicles/dictionaries/statuses/{custom.id}/').status_code == 400
        self.vehicle.status = 'PURCHASED'
        self.vehicle.save()
        assert self.client.delete(f'/api/vehicles/dictionaries/statuses/{custom.id}/').status_code == 204

    def test_unknown_expense_currency_rejected(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(f'{self.url}expenses/', {'title': 'X', 'amount': '10', 'currency': 'XYZ'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_make_and_model_synced_to_dictionary(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(self.url, {'make': 'Rivian', 'model': 'R1S'}, format='json')
        assert Make.objects.filter(name='Rivian').exists()
        assert VehicleModel.objects.filter(make__name='Rivian', name='R1S').exists()

    # --- Walýuta we girdeji ---

    def test_expenses_converted_to_usd_and_profit(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(self.url, {'purchase_price': '5000', 'purchase_currency': 'USD'}, format='json')
        self.client.post(f'{self.url}expenses/', {'title': 'Auksion', 'amount': '1000', 'currency': 'USD'}, format='json')
        self.client.post(f'{self.url}expenses/', {'title': 'Gümrük', 'amount': '350', 'currency': 'TMT'}, format='json')
        res = self.client.get(self.url)
        assert res.data['total_expenses'] == '1100.00'
        assert res.data['expenses_by_currency'] == {'TMT': '350.00', 'USD': '1000.00'}
        assert res.data['profit_usd'] is None

        self._handed_over(self.emp1)
        self.client.force_authenticate(self.emp1)
        res = self.client.patch(self.url, {'status': 'SOLD', 'sale_price': '28000', 'sale_currency': 'TMT',
                                           'buyer_name': 'Aman'}, format='json')
        assert res.status_code == 200
        assert res.data['sale_price_usd'] == '8000.00'
        assert res.data['profit_usd'] == '1900.00'
        assert res.data['sold_at'] is not None

    def test_rate_change_does_not_rewrite_old_expenses(self):
        exp = VehicleExpense.objects.create(vehicle=self.vehicle, title='A', amount=Decimal('350'), currency='TMT')
        assert exp.amount_usd == Decimal('100.00')
        Currency.objects.filter(code='TMT').update(usd_rate=Decimal('7'))
        exp.description = 'x'
        exp.save()
        exp.refresh_from_db()
        assert exp.amount_usd == Decimal('100.00')

    def test_leaving_sold_clears_sold_at(self):
        self.vehicle.status = 'SOLD'
        self.vehicle.save()
        assert self.vehicle.sold_at is not None
        self.vehicle.status = 'ARRIVED_TKM'
        self.vehicle.save()
        assert self.vehicle.sold_at is None

    # --- Tabşyryş: ret / ýatyrmak ---

    def _request_handover(self):
        self._handed_over(self.emp1)
        self.client.force_authenticate(self.emp1)
        assert self.client.post(self.url + 'handover/', {'employee_id': self.emp2.id}).status_code == 200

    def test_target_can_reject_handover(self):
        self._request_handover()
        assert Notification.objects.filter(user=self.emp2, kind='HANDOVER_REQUESTED').exists()
        self.client.force_authenticate(self.emp2)
        res = self.client.post(self.url + 'reject-handover/', {'note': 'Maşyn zaýa'})
        assert res.status_code == 200
        self.vehicle.refresh_from_db()
        assert self.vehicle.pending_handover_owner is None and self.vehicle.current_owner == self.emp1
        assert Notification.objects.filter(user=self.emp1, kind='HANDOVER_REJECTED').exists()
        assert self.vehicle.history_logs.filter(event=Event.HANDOVER_REJECTED).exists()

    def test_initiator_can_cancel_but_others_cannot(self):
        self._request_handover()
        self.client.force_authenticate(self.emp2)
        assert self.client.post(self.url + 'cancel-handover/').status_code == 403
        self.client.force_authenticate(self.emp1)
        assert self.client.post(self.url + 'cancel-handover/').status_code == 200
        self.vehicle.refresh_from_db()
        assert self.vehicle.pending_handover_owner is None

    def test_admin_can_cancel_pending_handover(self):
        self._request_handover()
        self.client.force_authenticate(self.admin)
        assert self.client.post(self.url + 'cancel-handover/').status_code == 200

    # --- Admin mejbury hereketleri ---

    def test_admin_force_reassign_requires_reason(self):
        self._handed_over(self.emp1)
        self.client.force_authenticate(self.admin)
        assert self.client.post(self.url + 'force-reassign/', {'employee_id': self.emp2.id}).status_code == 400
        res = self.client.post(self.url + 'force-reassign/', {'employee_id': self.emp2.id, 'note': 'Işden gitdi'})
        assert res.status_code == 200
        self.vehicle.refresh_from_db()
        assert self.vehicle.current_owner == self.emp2 and self.vehicle.is_handed_over
        assert self.vehicle.history_logs.filter(event=Event.REASSIGNED).exists()

    def test_employee_cannot_force_reassign(self):
        self._handed_over(self.emp1)
        self.client.force_authenticate(self.emp1)
        res = self.client.post(self.url + 'force-reassign/', {'employee_id': self.emp2.id, 'note': 'x'})
        assert res.status_code == 403

    def test_admin_revoke_handover_restores_admin_control(self):
        self._handed_over(self.emp1)
        self.client.force_authenticate(self.admin)
        assert self.client.patch(self.url, {'mileage': 5}, format='json').status_code == 403
        assert self.client.post(self.url + 'revoke-handover/', {'note': 'Barlag'}).status_code == 200
        assert self.client.patch(self.url, {'mileage': 5}, format='json').status_code == 200

    # --- Audit / çykdajy üýtgetmek ---

    def test_expense_edit_and_delete_are_logged(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(f'{self.url}expenses/', {'title': 'A', 'amount': '10', 'currency': 'USD'}, format='json')
        assert res.status_code == 201
        exp_id = res.data['id']
        res = self.client.patch(f'{self.url}expenses/{exp_id}/', {'amount': '20'}, format='json')
        assert res.status_code == 200 and res.data['amount_usd'] == '20.00'
        assert self.client.delete(f'{self.url}expenses/{exp_id}/').status_code == 204
        events = set(self.vehicle.history_logs.values_list('event', flat=True))
        assert {Event.EXPENSE_ADDED, Event.EXPENSE_UPDATED, Event.EXPENSE_DELETED} <= events

    def test_assigned_employee_cannot_edit_expense(self):
        exp = VehicleExpense.objects.create(vehicle=self.vehicle, title='A', amount=10)
        self.client.force_authenticate(self.emp1)
        assert self.client.patch(f'{self.url}expenses/{exp.id}/', {'amount': '1'}, format='json').status_code == 403

    # --- Işgärler / parol ---

    def test_admin_can_deactivate_employee_and_they_cannot_login(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f'/api/auth/employees/{self.emp2.id}/', {'is_active': False, 'first_name': 'Täze'}, format='json')
        assert res.status_code == 200 and res.data['is_active'] is False
        self.client.force_authenticate(None)
        res = self.client.post('/api/auth/token/', {'username': 'emp2', 'password': 'Pass123!x'})
        assert res.status_code == 401

    def test_employee_cannot_edit_employees(self):
        self.client.force_authenticate(self.emp1)
        assert self.client.patch(f'/api/auth/employees/{self.emp2.id}/', {'is_active': False}, format='json').status_code == 403

    def test_change_own_password(self):
        self.client.force_authenticate(self.emp1)
        bad = self.client.post('/api/auth/me/change-password/', {'old_password': 'wrong', 'new_password': 'NewStrong#2026'})
        assert bad.status_code == 400
        ok = self.client.post('/api/auth/me/change-password/', {'old_password': 'Pass123!x', 'new_password': 'NewStrong#2026'})
        assert ok.status_code == 200
        self.emp1.refresh_from_db()
        assert self.emp1.check_password('NewStrong#2026')

    def test_profile_update_cannot_change_role(self):
        self.client.force_authenticate(self.emp1)
        res = self.client.patch('/api/auth/me/', {'role': 'ADMIN', 'telegram_chat_id': '123'}, format='json')
        assert res.status_code == 200
        self.emp1.refresh_from_db()
        assert self.emp1.role == User.Role.EMPLOYEE and self.emp1.telegram_chat_id == '123'

    # --- Hasabatlar ---

    def test_month_range_filters_by_month_not_only_year(self):
        old = timezone.now().replace(month=1, day=15)
        Vehicle.objects.filter(pk=self.vehicle.pk).update(created_at=old)
        self.client.force_authenticate(self.admin)
        y = old.year
        res = self.client.get('/api/vehicles/reports/summary/', {
            'period_type': 'month_range', 'start_month': f'{y}-03', 'end_month': f'{y}-12'})
        assert res.data['kpis']['total_vehicles'] == 0
        res = self.client.get('/api/vehicles/reports/summary/', {
            'period_type': 'month_range', 'start_month': f'{y}-01', 'end_month': f'{y}-01'})
        assert res.data['kpis']['total_vehicles'] == 1

    def test_report_by_sold_date(self):
        self.vehicle.status = 'SOLD'
        self.vehicle.sale_price = Decimal('9000')
        self.vehicle.purchase_price = Decimal('5000')
        self.vehicle.save()
        Vehicle.objects.create(vin='FEATVIN000000002', title='U', make='A', model='B', year=2020, color='Gara')
        self.client.force_authenticate(self.admin)
        today = timezone.localdate().isoformat()
        res = self.client.get('/api/vehicles/reports/summary/', {'date_basis': 'sold', 'period_type': 'day', 'date': today})
        k = res.data['kpis']
        assert k['total_vehicles'] == 1 and k['sold_count'] == 1
        assert k['total_profit_usd'] == '4000.00'

    def test_export_xlsx(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get('/api/vehicles/reports/export/', {'file_format': 'xlsx'})
        assert res.status_code == 200
        assert res['Content-Type'].startswith('application/vnd.openxmlformats')
        res = self.client.get('/api/vehicles/reports/export/', {'file_format': 'csv'})
        assert res.status_code == 200 and 'FEATVIN000000001' in res.content.decode('utf-8')

    def test_dashboard_admin_only_and_lists_stale(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(status_changed_at=timezone.now() - timedelta(days=90))
        self.client.force_authenticate(self.emp1)
        assert self.client.get('/api/vehicles/reports/dashboard/').status_code == 403
        self.client.force_authenticate(self.admin)
        res = self.client.get('/api/vehicles/reports/dashboard/')
        assert res.status_code == 200
        assert res.data['counts']['stale_vehicles'] == 1
        assert any(e['username'] == 'emp1' and e['total'] == 1 for e in res.data['employees'])

    def test_stage_durations(self):
        self.client.force_authenticate(self.admin)
        self.client.post(self.url + 'update-status-location/', {'status': 'IN_TRANSIT'})
        res = self.client.get(self.url + 'stage-durations/')
        assert res.status_code == 200
        assert [s['status'] for s in res.data['stages']][-1] == 'IN_TRANSIT'

    # --- Bildirişler ---

    def test_notifications_list_and_mark_read(self):
        self._request_handover()
        self.client.force_authenticate(self.emp2)
        assert self.client.get('/api/notifications/unread-count/').data['count'] == 1
        items = self.client.get('/api/notifications/').data
        assert self.client.post(f"/api/notifications/{items[0]['id']}/read/").status_code == 200
        assert self.client.get('/api/notifications/unread-count/').data['count'] == 0
        # Başga ulanyjynyň bildirişini okap bolmaýar
        self.client.force_authenticate(self.emp1)
        assert self.client.post(f"/api/notifications/{items[0]['id']}/read/").status_code == 404
