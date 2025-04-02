# Generated by Django 2.2.28 between 2023-03-12 17:28 and 2023-03-22 13:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0003_merge_20250331_2336'),
    ]


    operations = [
        # Altering some fields to add defaults before removing them, so the deletions are invertible
        migrations.AlterField(
            model_name='registration',
            name='classical_rating',
            field=models.PositiveIntegerField(verbose_name='rating', default=0),
        ),
        migrations.AlterField(
            model_name='registration',
            name='peak_classical_rating',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='peak rating', default=0),
        ),
        migrations.AlterField(
            model_name='registration',
            name='already_in_slack_group',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='registration',
            name='classical_rating',
        ),
        migrations.RemoveField(
            model_name='registration',
            name='peak_classical_rating',
        ),
        migrations.RemoveField(
            model_name='registration',
            name='already_in_slack_group',
        ),
        migrations.RemoveField(
            model_name='registration',
            name='previous_season_alternate',
        ),
        migrations.RemoveField(
            model_name='registration',
            name='slack_username',
        ),
    ]
