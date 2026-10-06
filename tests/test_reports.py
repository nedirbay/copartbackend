import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from vehicles.models import Vehicle, VehicleExpense, VehicleStatus, VehicleLocation

User = get_user_model()

@pytest.mark.django_db
class TestReportsSummary:

    def setup_method(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='reports_admin', password='Password123!')
        self.emp = User.objects.create_user(username='reports_emp', password='Password123!', role=User.Role.EMPLOYEE)

        self.v1 = Vehicle.objects.create(
            vin='VINREPORT1111111',
            title='Toyota Camry 2022',
            make='Toyota',
            model='Camry',
            year=2022,
            color='White',
            status=VehicleStatus.PURCHASED,
            location=VehicleLocation.USA_COPART,
            current_owner=self.emp
        )

        VehicleExpense.objects.create(
            vehicle=self.v1,
            title='Auction Fee',
            amount='500.00',
            stage='USA'
        )

    def test_reports_summary_all_period(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/vehicles/reports/summary/?period_type=all')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['kpis']['total_vehicles'] >= 1
        assert float(res.data['kpis']['total_expenses_usd']) >= 500.00

    def test_reports_summary_day_filter(self):
        self.client.force_authenticate(user=self.admin)
        today_str = self.v1.created_at.strftime('%Y-%m-%d')
        res = self.client.get(f'/api/vehicles/reports/summary/?period_type=day&date={today_str}')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['kpis']['total_vehicles'] >= 1
