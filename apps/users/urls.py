from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    UserProfileView, EmployeeListCreateView, EmployeeResetPasswordView, EmployeeLookupView,
    EmployeeDetailView, ChangePasswordView,
)

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user_profile'),
    path('me/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('employees/', EmployeeListCreateView.as_view(), name='employee_list_create'),
    path('employees/lookup/', EmployeeLookupView.as_view(), name='employee_lookup'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<int:pk>/reset-password/', EmployeeResetPasswordView.as_view(), name='employee_reset_password'),
]

