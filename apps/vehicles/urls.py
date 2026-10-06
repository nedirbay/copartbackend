from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet, VehicleExpenseViewSet, VehicleDocumentViewSet,
    DynamicVehicleStatusViewSet, DynamicVehicleLocationViewSet,
    MakeViewSet, VehicleModelViewSet, CurrencyViewSet, ExpenseTypeViewSet
)

router = DefaultRouter()
router.register(r'dictionaries/statuses', DynamicVehicleStatusViewSet, basename='dict-status')
router.register(r'dictionaries/locations', DynamicVehicleLocationViewSet, basename='dict-location')
router.register(r'dictionaries/makes', MakeViewSet, basename='dict-make')
router.register(r'dictionaries/models', VehicleModelViewSet, basename='dict-model')
router.register(r'dictionaries/currencies', CurrencyViewSet, basename='dict-currency')
router.register(r'dictionaries/expense-types', ExpenseTypeViewSet, basename='dict-expense-type')
router.register(r'', VehicleViewSet, basename='vehicle')


expense_list = VehicleExpenseViewSet.as_view({
    'get': 'list',
    'post': 'create'
})
expense_detail = VehicleExpenseViewSet.as_view({
    'get': 'retrieve',
    'delete': 'destroy'
})

document_list = VehicleDocumentViewSet.as_view({
    'get': 'list',
    'post': 'create'
})
document_detail = VehicleDocumentViewSet.as_view({
    'get': 'retrieve',
    'delete': 'destroy'
})

urlpatterns = [
    path('<str:vehicle_vin>/expenses/', expense_list, name='vehicle-expense-list'),
    path('<str:vehicle_vin>/expenses/<int:pk>/', expense_detail, name='vehicle-expense-detail'),
    path('<str:vehicle_vin>/documents/', document_list, name='vehicle-document-list'),
    path('<str:vehicle_vin>/documents/<int:pk>/', document_detail, name='vehicle-document-detail'),
    path('', include(router.urls)),
]
