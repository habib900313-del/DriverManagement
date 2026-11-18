from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0007_allow_archived_driver_code_reuse"),
    ]

    operations = [
        migrations.AddField(
            model_name="driver",
            name="period_calendar",
            field=models.CharField(
                choices=[
                    ("gregorian", "میلادی — دوره‌های قبلی"),
                    ("jalali", "هجری شمسی"),
                ],
                default="gregorian",
                max_length=16,
                verbose_name="تقویم دوره‌های مالی",
            ),
        ),
        migrations.AlterField(
            model_name="driver",
            name="period_calendar",
            field=models.CharField(
                choices=[
                    ("gregorian", "میلادی — دوره‌های قبلی"),
                    ("jalali", "هجری شمسی"),
                ],
                default="jalali",
                max_length=16,
                verbose_name="تقویم دوره‌های مالی",
            ),
        ),
    ]
