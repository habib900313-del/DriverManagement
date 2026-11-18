from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0006_add_driver_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="driver",
            name="uniq_driver_code_case_insensitive",
        ),
        migrations.AlterField(
            model_name="driver",
            name="driver_code",
            field=models.CharField(
                help_text="شماره مسلسل دستی و یکتای راننده",
                max_length=50,
                verbose_name="شماره مسلسل",
            ),
        ),
    ]
