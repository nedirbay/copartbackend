from django.db import models
from django.conf import settings

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

class Vehicle(models.Model):
    vin = models.CharField(max_length=17, primary_key=True, help_text="Unique VIN Code")
    title = models.CharField(max_length=100, help_text="Vehicle title / name")
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.PositiveIntegerField()
    color = models.CharField(max_length=30)
    mileage = models.PositiveIntegerField(default=0)
    
    status = models.CharField(
        max_length=30,
        choices=VehicleStatus.choices,
        default=VehicleStatus.PURCHASED
    )
    location = models.CharField(
        max_length=50,
        choices=VehicleLocation.choices,
        default=VehicleLocation.USA_COPART
    )
    
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.vin} - {self.make} {self.model} ({self.year})"

class VehicleHistoryLog(models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='history_logs'
    )
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
    description = models.TextField(blank=True, default='')
    stage = models.CharField(max_length=50, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

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
