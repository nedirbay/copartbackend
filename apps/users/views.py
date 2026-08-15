from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from .serializers import UserSerializer, EmployeeCreateSerializer, EmployeeCreatedResponseSerializer
from .permissions import IsAdminUserRole
from .services import create_employee_service

User = get_user_model()

class UserProfileView(generics.RetrieveAPIView):
    """
    Get current logged in user profile.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

class EmployeeListCreateView(generics.ListCreateAPIView):
    """
    Admin can list employees or create a new employee with 16-char random password.
    """
    permission_classes = [IsAdminUserRole]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(role=User.Role.EMPLOYEE).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = EmployeeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        employee, raw_password = create_employee_service(
            username=serializer.validated_data['username'],
            first_name=serializer.validated_data['first_name'],
            last_name=serializer.validated_data['last_name'],
            email=serializer.validated_data.get('email', ''),
            phone_number=serializer.validated_data.get('phone_number', '')
        )
        
        res_serializer = EmployeeCreatedResponseSerializer(employee)
        data = res_serializer.data
        data['generated_password'] = raw_password
        
        return Response(data, status=status.HTTP_201_CREATED)
