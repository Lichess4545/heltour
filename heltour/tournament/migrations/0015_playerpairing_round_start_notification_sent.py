from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournament", "0014_alter_broadcast_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerpairing",
            name="round_start_notification_sent",
            field=models.BooleanField(default=None, null=True),
        ),
    ]
