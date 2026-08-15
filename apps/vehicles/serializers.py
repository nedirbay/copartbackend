from rest_framework import serializers
from django.db.models import Sum
from .models import Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument
from users.serializers import UserSerializer

class VehicleHistoryLogSerializer(serializers.ModelSerializer):
    owner_detail = UserSerializer(source='owner', read_only=True)
    changed_by_detail = UserSerializer(source='changed_by', read_only=True)

    class Meta:
        model = VehicleHistoryLog
        fields = [
            'id', 'vehicle', 'status', 'location', 
            'owner', 'owner_detail', 'changed_by', 'changed_by_detail', 
            'note', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class VehicleExpenseSerializer(serializers.ModelSerializer):
    created_by_detail = UserSerializer(source='created_by', read_only=True)

    class Meta:
        model = VehicleExpense
        fields = [
            'id', 'vehicle', 'title', 'amount', 'currency', 
            'description', 'stage', 'created_by', 'created_by_detail', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'created_by', 'vehicle']

class VehicleDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_detail = UserSerializer(source='uploaded_by', read_only=True)

    class Meta:
        model = VehicleDocument
        fields = [
            'id', 'vehicle', 'file', 'title', 'document_type', 
            'uploaded_by', 'uploaded_by_detail', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'uploaded_by', 'vehicle']

class VehicleSerializer(serializers.ModelSerializer):
    current_owner_detail = UserSerializer(source='current_owner', read_only=True)
    total_expenses = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            'vin', 'title', 'make', 'model', 'year', 'color', 'mileage',
            'status', 'location', 'current_owner', 'current_owner_detail',
            'is_handed_over', 'total_expenses', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_handed_over']

    def get_total_expenses(self, obj):
        total = obj.expenses.aggregate(total=Sum('amount'))['total']
        return f"{total:.2f}" if total is not None else "0.00"

class VehicleUpdateStatusLocationSerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

class VehicleHandoverSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True)
