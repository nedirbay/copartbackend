from django.contrib import admin
from .models import (
    Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType
)

@admin.register(DynamicVehicleStatus)
class DynamicVehicleStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name')
    search_fields = ('code', 'name')

@admin.register(DynamicVehicleLocation)
class DynamicVehicleLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name')
    search_fields = ('code', 'name')

@admin.register(Make)
class MakeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'make', 'name')
    list_filter = ('make',)
    search_fields = ('name', 'make__name')

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'symbol')
    search_fields = ('code', 'name')

@admin.register(ExpenseType)
class ExpenseTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('vin', 'make', 'model', 'year', 'status', 'location', 'current_owner', 'is_handed_over')
    list_filter = ('status', 'location', 'is_handed_over')
    search_fields = ('vin', 'make', 'model')

@admin.register(VehicleHistoryLog)
class VehicleHistoryLogAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'status', 'location', 'owner', 'changed_by', 'created_at')
    search_fields = ('vehicle__vin', 'note')

@admin.register(VehicleExpense)
class VehicleExpenseAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'title', 'amount', 'currency', 'created_by', 'created_at')
    search_fields = ('vehicle__vin', 'title')

@admin.register(VehicleDocument)
class VehicleDocumentAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'title', 'document_type', 'uploaded_by', 'created_at')
    search_fields = ('vehicle__vin', 'title')

