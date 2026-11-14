from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.conf import settings
from django.utils import timezone

class VehicleStatus(models.TextChoices):
    PURCHASED = 'PURCHASED', 'Satyn alyndy'
    IN_TRANSIT = 'IN_TRANSIT', 'Ýolda'
    ARRIVED_TKM = 'ARRIVED_TKM', 'Türkmenistana geldi'
    SOLD = 'SOLD', 'Satyldy'

class VehicleLocation(models.TextChoices):
    USA_COPART = 'USA_COPART', 'Amerika (Copart)'
    SHIPPING_TRANSIT = 'SHIPPING_TRANSIT', 'Ýük daşama ýola çykaryldy'
    GEORGIA = 'GEORGIA', 'Gruziýa'
    TURKMENISTAN_INTERNAL = 'TURKMENISTAN_INTERNAL', 'Türkmenistan (Içerki ýerleri)'

# Ulgamyň logikasy daýanýan kodlar: sözlükden pozulyp bilinmeýär
SYSTEM_STATUS_CODES = {c.value for c in VehicleStatus}
SYSTEM_LOCATION_CODES = {c.value for c in VehicleLocation}
BASE_CURRENCY = 'USD'


class DynamicVehicleStatus(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Vehicle Status"
        verbose_name_plural = "Vehicle Statuses"
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.code})"

class DynamicVehicleLocation(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Vehicle Location"
        verbose_name_plural = "Vehicle Locations"
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.code})"

class Make(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class VehicleModel(models.Model):
    make = models.ForeignKey(Make, on_delete=models.CASCADE, related_name='models')
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ['name']
        unique_together = ('make', 'name')

    def __str__(self):
        return f"{self.make.name} {self.name}"

class Currency(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10, default='$')
    usd_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal('1'),
        help_text="1 USD = näçe birlik (meselem TMT üçin 3.5)"
    )
    rate_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['id']

    def __str__(self):
        return f"{self.code} ({self.symbol})"

def to_usd(amount, currency_code):
    """Mukdary häzirki kurs boýunça USD-a öwürýär. Kurs tapylmasa None."""
    if amount is None:
        return None
    code = (currency_code or BASE_CURRENCY).upper()
    if code == BASE_CURRENCY:
        return Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    rate = Currency.objects.filter(code=code).values_list('usd_rate', flat=True).first()
    if not rate:
        return None
    return (Decimal(amount) / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ExpenseType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class Vehicle(models.Model):
    vin = models.CharField(max_length=17, primary_key=True, help_text="Unique VIN Code")
    title = models.CharField(max_length=100, help_text="Vehicle title / name")
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.PositiveIntegerField()
    color = models.CharField(max_length=30)
    mileage = models.PositiveIntegerField(default=0)
    photo = models.ImageField(upload_to='vehicles/%Y/%m/', null=True, blank=True, help_text="Vehicle primary photo")
    
    # Kodlar DynamicVehicleStatus / DynamicVehicleLocation sözlüklerinden alynýar (serializerde barlanýar)
    status = models.CharField(max_length=50, default=VehicleStatus.PURCHASED)
    location = models.CharField(max_length=50, default=VehicleLocation.USA_COPART)
    status_changed_at = models.DateTimeField(null=True, blank=True)

    # Logistika
    lot_number = models.CharField(max_length=30, blank=True, default='')
    auction_date = models.DateField(null=True, blank=True)
    container_number = models.CharField(max_length=30, blank=True, default='')
    eta = models.DateField(null=True, blank=True, help_text="Garaşylýan gelip ýetiş senesi")

    # Maliýe (USD bahalary girizilen pursatdaky kurs boýunça saklanýar)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    purchase_currency = models.CharField(max_length=10, default=BASE_CURRENCY)
    purchase_price_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_currency = models.CharField(max_length=10, default=BASE_CURRENCY)
    sale_price_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    # Alyjy
    buyer_name = models.CharField(max_length=150, blank=True, default='')
    buyer_phone = models.CharField(max_length=30, blank=True, default='')
    buyer_note = models.TextField(blank=True, default='')
    
    current_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_vehicles',
        help_text="Assigned owner/employee managing the vehicle"
    )
    is_handed_over = models.BooleanField(
        default=False,
        help_text="Indicates if handover process (e.g. in Georgia) has taken place"
    )
    pending_handover_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_handover_vehicles',
        help_text="Target employee waiting to confirm handover"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        old = None
        if not self._state.adding:
            old = Vehicle.objects.filter(pk=self.pk).values(
                'status', 'purchase_price', 'purchase_currency', 'sale_price', 'sale_currency'
            ).first()
        now = timezone.now()

        if old is None or old['status'] != self.status:
            self.status_changed_at = now
            if self.status == VehicleStatus.SOLD:
                self.sold_at = self.sold_at or now
            else:
                self.sold_at = None

        # USD bahasyny diňe baha ýa-da walýuta üýtgände täzeden hasaplaýarys (köne kurs saklanýar)
        if old is None or (old['purchase_price'], old['purchase_currency']) != (self.purchase_price, self.purchase_currency) \
                or (self.purchase_price is not None and self.purchase_price_usd is None):
            self.purchase_price_usd = to_usd(self.purchase_price, self.purchase_currency)
        if old is None or (old['sale_price'], old['sale_currency']) != (self.sale_price, self.sale_currency) \
                or (self.sale_price is not None and self.sale_price_usd is None):
            self.sale_price_usd = to_usd(self.sale_price, self.sale_currency)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vin} - {self.make} {self.model} ({self.year})"

class VehicleHistoryLog(models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='history_logs'
    )
    class Event(models.TextChoices):
        CREATED = 'CREATED', 'Hasaba alyndy'
        UPDATED = 'UPDATED', 'Maglumat üýtgedildi'
        STATUS = 'STATUS', 'Status / ýer'
        ASSIGNED = 'ASSIGNED', 'Berkidildi'
        HANDOVER_REQUESTED = 'HANDOVER_REQUESTED', 'Tabşyryş haýyşy'
        HANDOVER_CONFIRMED = 'HANDOVER_CONFIRMED', 'Kabul edildi'
        HANDOVER_REJECTED = 'HANDOVER_REJECTED', 'Ret edildi'
        HANDOVER_CANCELLED = 'HANDOVER_CANCELLED', 'Ýatyryldy'
        REASSIGNED = 'REASSIGNED', 'Admin täzeden berkitdi'
        HANDOVER_REVOKED = 'HANDOVER_REVOKED', 'Admin dolandyryşy yzyna aldy'
        EXPENSE_ADDED = 'EXPENSE_ADDED', 'Çykdajy goşuldy'
        EXPENSE_UPDATED = 'EXPENSE_UPDATED', 'Çykdajy üýtgedildi'
        EXPENSE_DELETED = 'EXPENSE_DELETED', 'Çykdajy pozuldy'
        DOCUMENT_ADDED = 'DOCUMENT_ADDED', 'Resminama goşuldy'
        DOCUMENT_DELETED = 'DOCUMENT_DELETED', 'Resminama pozuldy'

    event = models.CharField(max_length=30, choices=Event.choices, default=Event.UPDATED)
    status = models.CharField(max_length=50)
    location = models.CharField(max_length=100)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_owner_histories'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_changes'
    )
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Log for {self.vehicle_id} at {self.created_at} ({self.status} / {self.location})"

class VehicleExpense(models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    stage = models.CharField(max_length=50, blank=True, default='')
    receipt = models.FileField(upload_to='expense_receipts/%Y/%m/', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        old = None
        if not self._state.adding:
            old = VehicleExpense.objects.filter(pk=self.pk).values('amount', 'currency').first()
        if old is None or (old['amount'], old['currency']) != (self.amount, self.currency) or self.amount_usd is None:
            self.amount_usd = to_usd(self.amount, self.currency)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vehicle_id} - {self.title}: {self.amount} {self.currency}"

class VehicleDocument(models.Model):
    class DocumentType(models.TextChoices):
        PHOTO = 'PHOTO', 'Surat (Photo)'
        AUCTION_DOC = 'AUCTION_DOC', 'Auksion Resminamasy'
        SHIPPING_DOC = 'SHIPPING_DOC', 'Ýük daşama Resminamasy'
        REPAIR_BILL = 'REPAIR_BILL', 'Ussa / Serhet çykdajysy'
        OTHER = 'OTHER', 'Başga'

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    file = models.FileField(upload_to='vehicle_docs/%Y/%m/')
    title = models.CharField(max_length=150)
    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
        default=DocumentType.PHOTO
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vehicle_id} - {self.title} ({self.document_type})"


class Notification(models.Model):
    """Programmanyň içindäki bildiriş (web we mobil üçin). Telegram goşmaça ugradylyp bilner."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    kind = models.CharField(max_length=30)
    message = models.CharField(max_length=500)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user_id}: {self.message[:40]}"
