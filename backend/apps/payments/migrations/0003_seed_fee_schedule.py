"""Seed the standard fee: 600 AFN per calendar quarter (C1), effective 1900-01-01.

created_by is NULL for this system row; every later FeeSchedule row (W11)
records the acting user.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

SEED_EFFECTIVE_FROM = date(1900, 1, 1)


def seed_fee_schedule(apps, schema_editor):
    FeeSchedule = apps.get_model("payments", "FeeSchedule")
    FeeSchedule.objects.get_or_create(
        effective_from=SEED_EFFECTIVE_FROM,
        defaults={
            "amount": Decimal("600.00"),
            "reason": "مبلغ استاندارد اولیه — 600 افغانی هر سه ماه تقویمی (C1)",
            "created_by": None,
        },
    )


def unseed_fee_schedule(apps, schema_editor):
    FeeSchedule = apps.get_model("payments", "FeeSchedule")
    FeeSchedule.objects.filter(
        effective_from=SEED_EFFECTIVE_FROM, created_by__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_invariant_triggers"),
    ]

    operations = [
        migrations.RunPython(seed_fee_schedule, unseed_fee_schedule),
    ]