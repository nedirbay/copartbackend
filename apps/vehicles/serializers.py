from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Vehicle, VehicleHistoryLog, VehicleExpense, VehicleDocument, Notification,
    DynamicVehicleStatus, DynamicVehicleLocation, Make, VehicleModel, Currency, ExpenseType,
    SYSTEM_STATUS_CODES, SYSTEM_LOCATION_CODES,
)


def validate_status_code(value):
    if value and not DynamicVehicleStatus.objects.filter(code=value).exists():
        raise serializers.ValidationError(f"'{value}' statusy sözlükde ýok.")
    return value


def validate_location_code(value):
    if value and not DynamicVehicleLocation.objects.filter(code=value).exists():
        raise serializers.ValidationError(f"'{value}' ýeri sözlükde ýok.")
    return value


def validate_currency_code(value):
    value = (value or '').upper()
    if not Currency.objects.filter(code=value).exists():
        raise serializers.ValidationError(f"'{value}' walýutasy sözlükde ýok.")
    return value


class CodeDictionaryMixin:
    """Awtoulaglarda ulanylýan kody üýtgetmek bolmaýar (awtoulaglar kody saklaýar)."""
    vehicle_field = None
    system_codes = set()

    def validate_code(self, value):
        value = value.strip().upper()
        if self.instance is not None and self.instance.code != value:
            if self.instance.code in self.system_codes:
                raise serializers.ValidationError("Ulgam kodyny üýtgedip bolmaýar.")
            if Vehicle.objects.filter(**{self.vehicle_field: self.instance.code}).exists():
                raise serializers.ValidationError("Bu kod awtoulaglarda ulanylýar, ony üýtgedip bolmaýar.")
        return value
from users.serializers import PublicUserSerializer

class DynamicVehicleStatusSerializer(CodeDictionaryMixin, serializers.ModelSerializer):
    vehicle_field = 'status'
    system_codes = SYSTEM_STATUS_CODES

    class Meta:
        model = DynamicVehicleStatus
        fields = ['id', 'code', 'name']

class DynamicVehicleLocationSerializer(CodeDictionaryMixin, serializers.ModelSerializer):
    vehicle_field = 'location'
    system_codes = SYSTEM_LOCATION_CODES

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
        fields = ['id', 'code', 'name', 'symbol', 'usd_rate', 'rate_updated_at']
        read_only_fields = ['rate_updated_at']

    def validate_code(self, value):
        value = value.strip().upper()
        if self.instance is not None and self.instance.code != value:
            if self.instance.code == 'USD':
                raise serializers.ValidationError("Esasy walýutanyň (USD) kodyny üýtgedip bolmaýar.")
            if VehicleExpense.objects.filter(currency=self.instance.code).exists():
                raise serializers.ValidationError("Bu walýuta çykdajylarda ulanylýar, kody üýtgedip bolmaýar.")
        return value

    def validate_usd_rate(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Kurs 0-dan uly bolmaly.")
        return value

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', ''))
        if code == 'USD' and 'usd_rate' in attrs and attrs['usd_rate'] != 1:
            raise serializers.ValidationError({"usd_rate": "USD kursy hemişe 1."})
        return attrs

class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = ['id', 'name']


class VehicleHistoryLogSerializer(serializers.ModelSerializer):
    owner_detail = PublicUserSerializer(source='owner', read_only=True)
    changed_by_detail = PublicUserSerializer(source='changed_by', read_only=True)

    class Meta:
        model = VehicleHistoryLog
        fields = [
            'id', 'vehicle', 'event', 'status', 'location',
            'owner', 'owner_detail', 'changed_by', 'changed_by_detail',
            'note', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class VehicleExpenseSerializer(serializers.ModelSerializer):
    created_by_detail = PublicUserSerializer(source='created_by', read_only=True)

    class Meta:
        model = VehicleExpense
        fields = [
            'id', 'vehicle', 'title', 'amount', 'currency', 'amount_usd',
            'description', 'stage', 'receipt', 'created_by', 'created_by_detail', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'vehicle', 'amount_usd']
        extra_kwargs = {'receipt': {'required': False, 'allow_null': True}}

    def validate_currency(self, value):
        return validate_currency_code(value)

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Mukdar 0-dan uly bolmaly.")
        return value

class VehicleDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_detail = PublicUserSerializer(source='uploaded_by', read_only=True)

    class Meta:
        model = VehicleDocument
        fields = [
            'id', 'vehicle', 'file', 'title', 'document_type', 
            'uploaded_by', 'uploaded_by_detail', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'uploaded_by', 'vehicle']

class VehicleSerializer(serializers.ModelSerializer):
    current_owner_detail = PublicUserSerializer(source='current_owner', read_only=True)
    pending_handover_owner_detail = PublicUserSerializer(source='pending_handover_owner', read_only=True)
    total_expenses = serializers.SerializerMethodField()
    expenses_by_currency = serializers.SerializerMethodField()
    profit_usd = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            'vin', 'title', 'make', 'model', 'year', 'color', 'mileage',
            'status', 'location', 'status_changed_at', 'current_owner', 'current_owner_detail',
            'pending_handover_owner', 'pending_handover_owner_detail',
            'is_handed_over',
            'lot_number', 'auction_date', 'container_number', 'eta',
            'purchase_price', 'purchase_currency', 'purchase_price_usd',
            'sale_price', 'sale_currency', 'sale_price_usd', 'sold_at',
            'buyer_name', 'buyer_phone', 'buyer_note',
            'total_expenses', 'expenses_by_currency', 'profit_usd',
            'photo', 'photo_url', 'photos', 'created_at', 'updated_at'
        ]
        # Tabşyryş ýagdaýy diňe ýörite hereketler (assign/handover/confirm) arkaly üýtgeýär
        read_only_fields = [
            'created_at', 'updated_at', 'is_handed_over', 'pending_handover_owner',
            'status_changed_at', 'purchase_price_usd', 'sale_price_usd', 'sold_at',
        ]
        extra_kwargs = {
            'photo': {'required': False, 'allow_null': True}
        }

    def validate_status(self, value):
        return validate_status_code(value)

    def validate_location(self, value):
        return validate_location_code(value)

    def validate_purchase_currency(self, value):
        return validate_currency_code(value)

    def validate_sale_currency(self, value):
        return validate_currency_code(value)

    def validate(self, attrs):
        for field in ('purchase_price', 'sale_price'):
            if attrs.get(field) is not None and attrs[field] < 0:
                raise serializers.ValidationError({field: "Baha otrisatel bolup bilmez."})
        return attrs

    def get_total_expenses(self, obj):
        """Ähli çykdajylar USD-da (her çykdajy girizilen pursatdaky kurs boýunça)."""
        total = obj.expenses.aggregate(total=Sum('amount_usd'))['total']
        return f"{total:.2f}" if total is not None else "0.00"

    def get_expenses_by_currency(self, obj):
        rows = obj.expenses.values('currency').annotate(total=Sum('amount')).order_by('currency')
        return {r['currency']: f"{r['total']:.2f}" for r in rows}

    def get_profit_usd(self, obj):
        """Girdeji = satuw − satyn alyş − çykdajylar (USD). Satuw bahasy ýok bolsa None."""
        if obj.sale_price_usd is None:
            return None
        expenses = obj.expenses.aggregate(total=Sum('amount_usd'))['total'] or 0
        return f"{obj.sale_price_usd - (obj.purchase_price_usd or 0) - expenses:.2f}"

    def _abs_url(self, f):
        request = self.context.get('request')
        try:
            return request.build_absolute_uri(f.url) if request else f.url
        except Exception:
            return f.url

    def get_photos(self, obj):
        urls = []
        if obj.photo:
            urls.append(self._abs_url(obj.photo))
        for doc in obj.documents.filter(document_type='PHOTO').order_by('created_at'):
            if doc.file:
                urls.append(self._abs_url(doc.file))
        return urls

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
    status = serializers.CharField(required=False, allow_blank=True, validators=[validate_status_code])
    location = serializers.CharField(required=False, allow_blank=True, validators=[validate_location_code])
    note = serializers.CharField(required=False, allow_blank=True)

class VehicleHandoverSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True)

class VehicleAssignSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True)



class ReasonSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default='')


class RequiredReasonSerializer(serializers.Serializer):
    note = serializers.CharField(required=True, allow_blank=False, error_messages={
        'required': "Sebäbini ýazmak hökmany.", 'blank': "Sebäbini ýazmak hökmany.",
    })


class ForceReassignSerializer(RequiredReasonSerializer):
    employee_id = serializers.IntegerField(required=True)


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=['android', 'ios', 'web'], default='android')


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'vehicle', 'kind', 'message', 'is_read', 'created_at']
        read_only_fields = fields
