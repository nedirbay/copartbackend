from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrator'
        EMPLOYEE = 'EMPLOYEE', 'Employee (Işgär)'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE
    )
    phone_number = models.CharField(max_length=30, blank=True, null=True)
    raw_password = models.CharField(max_length=128, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_employee_role(self):
        return self.role == self.Role.EMPLOYEE

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
