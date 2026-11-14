import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()

@pytest.mark.django_db
class TestUsers:

    def setup_method(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username='admin_copart',
            password='AdminPassword123!',
            email='admin@copart.com',
            role=User.Role.ADMIN
        )
        self.employee_user = User.objects.create_user(
            username='employee_john',
            password='EmployeePass123!',
            first_name='John',
            last_name='Doe',
            role=User.Role.EMPLOYEE
        )

    def test_jwt_login_admin(self):
        response = self.client.post('/api/auth/token/', {
            'username': 'admin_copart',
            'password': 'AdminPassword123!'
        })
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_admin_create_employee_with_16_char_password(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'username': 'isgar_merdan',
            'first_name': 'Merdan',
            'last_name': 'Annamyradow',
            'email': 'merdan@example.com',
            'phone_number': '+99365123456'
        }
        response = self.client.post('/api/auth/employees/', payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['username'] == 'isgar_merdan'
        assert response.data['role'] == User.Role.EMPLOYEE
        
        # Verify 16 character generated password
        gen_pass = response.data['generated_password']
        assert len(gen_pass) == 16
        
        # Test employee can log in with generated password
        login_res = self.client.post('/api/auth/token/', {
            'username': 'isgar_merdan',
            'password': gen_pass
        })
        assert login_res.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_employee(self):
        self.client.force_authenticate(user=self.employee_user)
        payload = {
            'username': 'isgar_durdy',
            'first_name': 'Durdy',
            'last_name': 'Gurbangeldiyew'
        }
        response = self.client.post('/api/auth/employees/', payload)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_employee_lookup_available_to_employee():
    """Employees can fetch a minimal colleague list (for handover) without passwords."""
    import pytest  # noqa: F401
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    User = get_user_model()
    emp = User.objects.create_user(username='lk_emp1', password='x', role=User.Role.EMPLOYEE)
    User.objects.create_user(username='lk_emp2', password='y', role=User.Role.EMPLOYEE, first_name='Aý')
    client = APIClient()
    client.force_authenticate(emp)
    res = client.get('/api/auth/employees/lookup/')
    assert res.status_code == 200
    names = {u['username'] for u in res.data}
    assert {'lk_emp1', 'lk_emp2'} <= names
    assert all(set(u.keys()) == {'id', 'username', 'first_name', 'last_name'} for u in res.data)
