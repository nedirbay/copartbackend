import secrets
import string
from django.contrib.auth import get_user_model

User = get_user_model()

def generate_random_password(length=16):
    """
    Generates a secure random 16-character password containing
    uppercase, lowercase letters, digits, and special characters.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure password has at least one lowercase, uppercase, digit, and symbol
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password

def create_employee_service(username, first_name, last_name, phone_number=""):
    """
    Service to create a new employee with an auto-generated 16-character password.
    Returns (user_instance, raw_password).
    """
    raw_password = generate_random_password(16)
    employee = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        password=raw_password,
        role=User.Role.EMPLOYEE
    )
    employee.raw_password = raw_password
    employee.save()
    return employee, raw_password

