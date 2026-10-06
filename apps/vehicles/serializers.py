from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType
)
from users.serializers import UserSerializer

class DynamicVehicleStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicVehicleStatus
        fields = ['id', 'code', 'name']

class DynamicVehicleLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicVehicleLocation
        fields = ['id', 'code', 'name']

class MakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Make
        fields = ['id', 'name']

class VehicleModelSerializer(serializers.ModelSerializer):
    make_name = serializers.ReadOnlyField(source='make.name')

    class Meta:
        model = VehicleModel
        fields = ['id', 'make', 'make_name', 'name']

class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['id', 'code', 'name', 'symbol']

class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = ['id', 'name']


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
    pending_handover_owner_detail = UserSerializer(source='pending_handover_owner', read_only=True)
    total_expenses = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            'vin', 'title', 'make', 'model', 'year', 'color', 'mileage',
            'status', 'location', 'current_owner', 'current_owner_detail',
            'pending_handover_owner', 'pending_handover_owner_detail',
            'is_handed_over', 'total_expenses', 'photo', 'photo_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_handed_over']
        extra_kwargs = {
            'photo': {'required': False, 'allow_null': True}
        }

    def get_total_expenses(self, obj):
        total = obj.expenses.aggregate(total=Sum('amount'))['total']
        return f"{total:.2f}" if total is not None else "0.00"

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo:
            try:
                return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
            except Exception:
                return obj.photo.url
        # Fallback to first PHOTO document if exists
        first_doc = obj.documents.filter(document_type='PHOTO').first()
        if first_doc and first_doc.file:
            try:
                return request.build_absolute_uri(first_doc.file.url) if request else first_doc.file.url
            except Exception:
                return first_doc.file.url
        return None

class VehicleUpdateStatusLocationSerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

class VehicleHandoverSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True)

class VehicleAssignSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True)

