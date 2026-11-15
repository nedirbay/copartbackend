"""FCM push: enjam tokenini hasaba almak we bildirişleri ugratmak (FCM HTTP galp)."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from vehicles import push
from vehicles.models import PushDevice, Vehicle

User = get_user_model()
VIN = 'PUSH0000000000001'


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.responses = {}  # token -> FakeResponse

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        return self.responses.get(json['message']['token'], FakeResponse())


@pytest.fixture
def fcm(settings, monkeypatch):
    settings.FIREBASE_CREDENTIALS_FILE = '/fake/service-account.json'
    session = FakeSession()
    monkeypatch.setattr(push, '_get_session', lambda: (session, 'demo-project'))
    monkeypatch.setattr(push, '_run_in_background', lambda fn, *args: fn(*args))
    return session


@pytest.fixture
def users(db):
    admin = User.objects.create_user(username='p_admin', password='x', role=User.Role.ADMIN)
    emp = User.objects.create_user(username='p_emp', password='x', role=User.Role.EMPLOYEE)
    return admin, emp


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def make_vehicle(owner):
    return Vehicle.objects.create(vin=VIN, title='Kia K5', make='Kia', model='K5', year=2022, color='Grey',
                                  current_owner=owner)


@pytest.mark.django_db
class TestDeviceRegistration:

    def test_register_and_move_between_users(self, users):
        admin, emp = users
        assert client_for(emp).post('/api/notifications/devices/', {'token': 'tok-1'}).status_code == 200
        assert PushDevice.objects.get(token='tok-1').user == emp
        # Şol telefonda başga ulanyjy girdi — token oňa geçýär (köne ulanyjynyň bildirişleri gitmez)
        client_for(admin).post('/api/notifications/devices/', {'token': 'tok-1'})
        assert PushDevice.objects.get(token='tok-1').user == admin
        assert PushDevice.objects.count() == 1

    def test_delete_only_own_token(self, users):
        admin, emp = users
        PushDevice.objects.create(user=emp, token='tok-1')
        client_for(admin).delete('/api/notifications/devices/', {'token': 'tok-1'}, format='json')
        assert PushDevice.objects.filter(token='tok-1').exists()
        res = client_for(emp).delete('/api/notifications/devices/', {'token': 'tok-1'}, format='json')
        assert res.status_code == 204 and not PushDevice.objects.exists()

    def test_requires_auth(self, db):
        assert APIClient().post('/api/notifications/devices/', {'token': 'x'}).status_code == 401


@pytest.mark.django_db(transaction=True)
class TestSending:

    def test_notification_is_pushed_to_owner_devices(self, users, fcm):
        admin, emp = users
        PushDevice.objects.create(user=emp, token='emp-phone')
        PushDevice.objects.create(user=admin, token='admin-phone')
        make_vehicle(admin)
        client_for(admin).post(f'/api/vehicles/{VIN}/assign/', {'employee_id': emp.id})

        assert len(fcm.calls) == 1  # diňe işgäre (Admin öz hereketi barada bildiriş almaýar)
        url, body = fcm.calls[0]
        assert url == 'https://fcm.googleapis.com/v1/projects/demo-project/messages:send'
        msg = body['message']
        assert msg['token'] == 'emp-phone' and msg['android']['priority'] == 'high'
        assert msg['data']['vehicle'] == VIN and msg['data']['kind'] == 'ASSIGNED'
        assert 'berkidildi' in msg['data']['message']
        assert msg['data']['id'].isdigit()
        assert all(isinstance(v, str) for v in msg['data'].values())  # FCM data diňe setir kabul edýär

    def test_dead_token_is_removed(self, users, fcm):
        admin, emp = users
        PushDevice.objects.create(user=emp, token='old-phone')
        PushDevice.objects.create(user=emp, token='new-phone')
        fcm.responses['old-phone'] = FakeResponse(404, {'error': {
            'status': 'NOT_FOUND', 'details': [{'errorCode': 'UNREGISTERED'}]}})
        make_vehicle(admin)
        client_for(admin).post(f'/api/vehicles/{VIN}/assign/', {'employee_id': emp.id})
        assert list(PushDevice.objects.values_list('token', flat=True)) == ['new-phone']

    def test_disabled_without_credentials(self, users, settings, monkeypatch):
        settings.FIREBASE_CREDENTIALS_FILE = ''
        called = []
        monkeypatch.setattr(push, '_run_in_background', lambda fn, *args: called.append(fn))
        admin, emp = users
        PushDevice.objects.create(user=emp, token='emp-phone')
        make_vehicle(admin)
        client_for(admin).post(f'/api/vehicles/{VIN}/assign/', {'employee_id': emp.id})
        assert called == []
