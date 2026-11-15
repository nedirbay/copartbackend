"""Real-time (WebSocket) wakalary: kime we haçan ugradylýar."""
import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from realtime import events
from vehicles.models import Vehicle, VehicleStatus, VehicleLocation

User = get_user_model()

VIN = 'RT000000000000001'


@pytest.fixture
def sent(monkeypatch):
    """Kanal gatlagyna gidýän habarlary ýygnaýar: [(group, payload), ...]"""
    log = []
    monkeypatch.setattr(events, '_send', lambda group, message: log.append((group, message['payload'])))
    return log


def groups_for(sent, event_type, **match):
    return sorted(
        g for g, p in sent
        if p['type'] == event_type and all(p.get(k) == v for k, v in match.items())
    )


@pytest.fixture
def users(db):
    admin = User.objects.create_user(username='rt_admin', password='x', role=User.Role.ADMIN)
    emp1 = User.objects.create_user(username='rt_emp1', password='x', role=User.Role.EMPLOYEE)
    emp2 = User.objects.create_user(username='rt_emp2', password='x', role=User.Role.EMPLOYEE)
    emp3 = User.objects.create_user(username='rt_emp3', password='x', role=User.Role.EMPLOYEE)
    return admin, emp1, emp2, emp3


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def make_vehicle(owner, handed_over=False):
    return Vehicle.objects.create(
        vin=VIN, title='Toyota Camry', make='Toyota', model='Camry', year=2020, color='Black',
        status=VehicleStatus.PURCHASED, location=VehicleLocation.USA_COPART,
        current_owner=owner, is_handed_over=handed_over,
    )


@pytest.mark.django_db(transaction=True)
class TestAudience:

    def test_create_vehicle_goes_to_admins_and_owner_once(self, users, sent):
        admin, emp1, emp2, _ = users
        sent.clear()
        res = client_for(admin).post('/api/vehicles/', {
            'vin': VIN, 'title': 'Camry', 'make': 'Toyota', 'model': 'Camry', 'year': 2020,
            'color': 'Black', 'current_owner': emp1.id,
        })
        assert res.status_code == 201
        # Bir hereket (awtoulag + taryh + bildiriş) her topara bir gezek
        assert groups_for(sent, 'vehicle.changed', vin=VIN) == ['role.admin', f'user.{emp1.id}']
        assert groups_for(sent, 'notifications.changed') == [f'user.{emp1.id}']
        assert not any(g == f'user.{emp2.id}' for g, _ in sent)

    def test_reassign_notifies_previous_owner_too(self, users, sent):
        admin, emp1, emp2, emp3 = users
        make_vehicle(emp1, handed_over=True)
        sent.clear()
        res = client_for(admin).post(f'/api/vehicles/{VIN}/force-reassign/', {'employee_id': emp2.id, 'note': 'işden gitdi'})
        assert res.status_code == 200
        # Öňki jogapkär hem habar alýar — sanawyndan aýyrmaly
        assert groups_for(sent, 'vehicle.changed', vin=VIN) == ['role.admin', f'user.{emp1.id}', f'user.{emp2.id}']
        assert not any(g == f'user.{emp3.id}' for g, _ in sent)

    def test_handover_request_reaches_target_employee(self, users, sent):
        admin, emp1, emp2, _ = users
        make_vehicle(emp1)
        sent.clear()
        res = client_for(emp1).post(f'/api/vehicles/{VIN}/handover/', {'employee_id': emp2.id})
        assert res.status_code == 200
        assert groups_for(sent, 'vehicle.changed', vin=VIN) == ['role.admin', f'user.{emp1.id}', f'user.{emp2.id}']
        assert groups_for(sent, 'notifications.changed') == [f'user.{emp2.id}']

    def test_expense_change_is_vehicle_change(self, users, sent):
        admin, emp1, *_ = users
        make_vehicle(emp1, handed_over=True)
        sent.clear()
        res = client_for(emp1).post(f'/api/vehicles/{VIN}/expenses/', {'title': 'Port', 'amount': '100'})
        assert res.status_code == 201
        assert groups_for(sent, 'vehicle.changed', vin=VIN) == ['role.admin', f'user.{emp1.id}']

    def test_delete_sends_only_deleted(self, users, sent):
        admin, emp1, *_ = users
        make_vehicle(emp1)
        client_for(admin).post(f'/api/vehicles/{VIN}/update-status-location/', {'status': VehicleStatus.IN_TRANSIT})
        sent.clear()
        res = client_for(admin).delete(f'/api/vehicles/{VIN}/')
        assert res.status_code == 204
        assert groups_for(sent, 'vehicle.deleted', vin=VIN) == ['role.admin', f'user.{emp1.id}']
        assert groups_for(sent, 'vehicle.changed', vin=VIN) == []

    def test_dictionary_change_goes_to_everyone(self, users, sent):
        admin, *_ = users
        sent.clear()
        res = client_for(admin).post('/api/vehicles/dictionaries/statuses/', {'code': 'AT_PORT', 'name': 'Portda'})
        assert res.status_code == 201
        assert groups_for(sent, 'dictionary.changed', name='statuses') == ['all']

    def test_deactivated_employee_is_disconnected(self, users, sent):
        admin, emp1, *_ = users
        sent.clear()
        res = client_for(admin).patch(f'/api/auth/employees/{emp1.id}/', {'is_active': False}, format='json')
        assert res.status_code == 200
        assert groups_for(sent, 'employees.changed') == ['role.admin']
        assert groups_for(sent, 'session.revoked') == [f'user.{emp1.id}']

    def test_mark_all_read_syncs_other_devices(self, users, sent):
        admin, emp1, *_ = users
        make_vehicle(admin)
        client_for(admin).post(f'/api/vehicles/{VIN}/assign/', {'employee_id': emp1.id})
        sent.clear()
        client_for(emp1).post('/api/notifications/read-all/')
        assert groups_for(sent, 'notifications.changed') == [f'user.{emp1.id}']

    def test_rolled_back_change_is_not_published(self, users, sent):
        _, emp1, *_ = users
        sent.clear()
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                make_vehicle(emp1)
                raise RuntimeError
        assert sent == []


@pytest.mark.django_db(transaction=True)
class TestWebsocket:

    def test_unauthenticated_connection_is_rejected(self):
        async def scenario():
            comm = WebsocketCommunicator(application, '/ws/?token=bad')
            await comm.connect()
            assert await comm.receive_output() == {'type': 'websocket.close', 'code': 4001}
        async_to_sync(scenario)()

    def test_employee_receives_events_only_for_own_vehicles(self, users):
        admin, emp1, emp2, _ = users
        api = client_for(admin)

        async def scenario():
            ws1 = WebsocketCommunicator(application, f'/ws/?token={AccessToken.for_user(emp1)}')
            ws2 = WebsocketCommunicator(application, f'/ws/?token={AccessToken.for_user(emp2)}')
            assert (await ws1.connect())[0] and (await ws2.connect())[0]
            assert (await ws1.receive_json_from())['type'] == 'hello'
            assert (await ws2.receive_json_from())['type'] == 'hello'

            await ws1.send_json_to({'type': 'ping'})
            assert await ws1.receive_json_from() == {'type': 'pong'}

            res = await sync_to_async(api.post)('/api/vehicles/', {
                'vin': VIN, 'title': 'Camry', 'make': 'Toyota', 'model': 'Camry', 'year': 2020,
                'color': 'Black', 'current_owner': emp1.id,
            })
            assert res.status_code == 201

            async def drain(ws):
                out = set()
                while not await ws.receive_nothing(timeout=0.3):
                    m = await ws.receive_json_from()
                    out.add((m['type'], m.get('vin') or m.get('name')))
                return out

            dict_events = {('dictionary.changed', 'makes'), ('dictionary.changed', 'models')}
            assert await drain(ws1) == {('vehicle.changed', VIN), ('notifications.changed', None)} | dict_events
            # emp2: awtoulag wakasy ýok, diňe umumy sözlük wakalary
            assert await drain(ws2) == dict_events

            await ws1.disconnect()
            await ws2.disconnect()
        async_to_sync(scenario)()

    def test_deactivation_closes_socket(self, users):
        admin, emp1, *_ = users
        api = client_for(admin)

        async def scenario():
            ws = WebsocketCommunicator(application, f'/ws/?token={AccessToken.for_user(emp1)}')
            assert (await ws.connect())[0]
            await ws.receive_json_from()  # hello
            await sync_to_async(api.patch)(f'/api/auth/employees/{emp1.id}/', {'is_active': False}, format='json')
            assert await ws.receive_json_from() == {'type': 'session.revoked'}
            assert await ws.receive_output() == {'type': 'websocket.close', 'code': 4003}
        async_to_sync(scenario)()
