# Generated by Django 2.2.28 on 2023-11-18 21:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0194_playerpairing_last_time_player_changed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registration',
            name='alternate_preference',
            field=models.CharField(blank=True, choices=[('alternate', 'Alternate'), ('full_time', 'Full Time'), ('either', 'Either is fine for me.')], max_length=255),
        ),
        migrations.AlterField(
            model_name='player',
            name='profile',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='registration',
            name='validation_ok',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
