"""Backfill the initial DriverFeeHistory row for every existing driver.

The current fee_start_date is the anchor of the current era (no prior history
exists). changed_by is the first superuser (fallback: first user). On a fresh
database with no drivers this is a no-op.
"""

from django.db import migrations


def backfill_fee_history(apps, schema_editor):
    Driver = apps.get_model("drivers", "Driver")
    DriverFeeHistory = apps.get_model("drivers", "DriverFeeHistory")
    User = apps.get_model("auth", "User")

    drivers = list(Driver.objects.all())
    if not drivers:
        return

    actor = User.objects.filter(is_superuser=True).order_by("id").first()
    if actor is None:
        actor = User.objects.order_by("id").first()
    if actor is None:
        raise RuntimeError(
            "Cannot backfill DriverFeeHistory: drivers exist but no user exists."
        )

    for driver in drivers:
        if DriverFeeHistory.objects.filter(driver_id=driver.pk).exists():
            continue
        DriverFeeHistory.objects.create(
            driver_id=driver.pk,
            old_fee_start_date=None,
            requested_fee_start_date=driver.fee_start_date,
            effective_fee_start_date=driver.fee_start_date,
            reason="ردیف اولیه — ثبت پیشین تاریخ شروع فیس (backfill ماژول مالی)",
            changed_by=actor,
        )


def remove_backfill(apps, schema_editor):
    DriverFeeHistory = apps.get_model("drivers", "DriverFeeHistory")
    DriverFeeHistory.objects.filter(
        old_fee_start_date__isnull=True,
        reason="ردیف اولیه — ثبت پیشین تاریخ شروع فیس (backfill ماژول مالی)",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0003_driverfeehistory"),
    ]

    operations = [
        migrations.RunPython(backfill_fee_history, remove_backfill),
    ]