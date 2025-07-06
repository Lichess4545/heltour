from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournament", "0009_alter_playernotificationsetting"),
    ]

    operations = [
        migrations.AddField(
            model_name="round",
            name="broadcast_rounds",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="broadcasts",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="create_broadcast",
            field=models.BooleanField(default=False),
        ),
    ]
