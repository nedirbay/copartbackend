from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from .serializers import UserSerializer, EmployeeCreateSerializer, EmployeeCreatedResponseSerializer
from .permissions import IsAdminUserRole
from .services import create_employee_service, generate_random_password

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
            phone_number=serializer.validated_data.get('phone_number', '')
        )
        
        res_serializer = EmployeeCreatedResponseSerializer(employee)
        data = res_serializer.data
        data['generated_password'] = raw_password
        
        return Response(data, status=status.HTTP_201_CREATED)

class EmployeeResetPasswordView(generics.GenericAPIView):
    """
    Admin resets password for employee and receives new 16-char plain password.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request, pk=None):
        employee = get_object_or_404(User, pk=pk, role=User.Role.EMPLOYEE)
        raw_password = generate_random_password(16)
        employee.set_password(raw_password)
        employee.raw_password = raw_password
        employee.save()

        return Response({
            "id": employee.id,
            "username": employee.username,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "new_password": raw_password,
            "message": "Parol üstünlikli täzelendi."
        }, status=status.HTTP_200_OK)


