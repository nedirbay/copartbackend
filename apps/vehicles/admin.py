from django.contrib import admin
from .models import Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument

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
