"""Bar bolan maglumatlary täze düzgünlere laýyklaşdyrýar."""
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations
from django.db.models import Max

STATUSES = [
    ('PURCHASED', 'Satyn alyndy'),
    ('IN_TRANSIT', 'Ýolda'),
    ('ARRIVED_TKM', 'Türkmenistana geldi'),
    ('SOLD', 'Satyldy'),
]
LOCATIONS = [
    ('USA_COPART', 'Amerika (Copart)'),
    ('SHIPPING_TRANSIT', 'Ýük daşama ýola çykaryldy'),
    ('GEORGIA', 'Gruziýa'),
    ('TURKMENISTAN_INTERNAL', 'Türkmenistan (Içerki ýerleri)'),
]
CURRENCIES = [('USD', 'Dollar ($)', '$', Decimal('1')), ('TMT', 'Manat (m.)', 'm.', Decimal('3.5')), ('EUR', 'Euro (€)', '€', Decimal('0.92'))]

EVENT_BY_NOTE = [
    ('Vehicle initial registration', 'CREATED'),
    ('Handover haýyşy', 'HANDOVER_REQUESTED'),
    ('Handover confirmed', 'HANDOVER_CONFIRMED'),
    ('berkidildi', 'ASSIGNED'),
    ('Updated status', 'STATUS'),
]


def forwards(apps, schema_editor):
    Status = apps.get_model('vehicles', 'DynamicVehicleStatus')
    Location = apps.get_model('vehicles', 'DynamicVehicleLocation')
    Currency = apps.get_model('vehicles', 'Currency')
    Vehicle = apps.get_model('vehicles', 'Vehicle')
    Expense = apps.get_model('vehicles', 'VehicleExpense')
    Log = apps.get_model('vehicles', 'VehicleHistoryLog')

    for code, name in STATUSES:
        Status.objects.get_or_create(code=code, defaults={'name': name})
    for code, name in LOCATIONS:
        Location.objects.get_or_create(code=code, defaults={'name': name})
    for code, name, symbol, rate in CURRENCIES:
        cur, created = Currency.objects.get_or_create(code=code, defaults={'name': name, 'symbol': symbol, 'usd_rate': rate})
        if not created and code != 'USD' and cur.usd_rate == 1:
            cur.usd_rate = rate
            cur.save(update_fields=['usd_rate'])

    # Awtoulaglarda bar bolan, ýöne sözlükde ýok kodlar sözlüge goşulýar
    for code in Vehicle.objects.values_list('status', flat=True).distinct():
        if code:
            Status.objects.get_or_create(code=code, defaults={'name': code})
    for code in Vehicle.objects.values_list('location', flat=True).distinct():
        if code:
            Location.objects.get_or_create(code=code, defaults={'name': code})
    for code in Expense.objects.values_list('currency', flat=True).distinct():
        if code:
            Currency.objects.get_or_create(code=code.upper(), defaults={'name': code.upper(), 'symbol': code.upper()})

    rates = {c.code: c.usd_rate for c in Currency.objects.all()}
    for exp in Expense.objects.filter(amount_usd__isnull=True):
        rate = rates.get((exp.currency or 'USD').upper())
        if rate:
            exp.amount_usd = (exp.amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            exp.save(update_fields=['amount_usd'])

    last_logs = dict(Log.objects.values('vehicle_id').annotate(last=Max('created_at')).values_list('vehicle_id', 'last'))
    for v in Vehicle.objects.all():
        v.status_changed_at = last_logs.get(v.vin) or v.updated_at
        if v.status == 'SOLD':
            v.sold_at = v.status_changed_at
        v.save(update_fields=['status_changed_at', 'sold_at'])

    for needle, event in EVENT_BY_NOTE:
        Log.objects.filter(event='UPDATED', note__icontains=needle).update(event=event)


class Migration(migrations.Migration):
    dependencies = [
        ('vehicles', '0005_finance_logistics_notifications'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
