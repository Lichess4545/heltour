"""Create demo leagues showcasing registration field flexibility."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from heltour.tournament.models import League, Season


class Command(BaseCommand):
    help = 'Create demo leagues showcasing flexible registration settings'

    def handle(self, *args, **options):
        demos = [
            {
                'name': 'Minimal Casual League',
                'tag': 'demo-minimal',
                'description': 'Casual tournament - only username needed',
                'require_name': False,
                'require_personal_email': False,
                'require_gender': False,
                'require_date_of_birth': False,
                'require_nationality': False,
                'require_corporate_email': False,
                'require_contact_number': False,
                'require_fide_id': False,
                'require_regional_rating': False,
                'regional_rating_name': '',
                'organisation_label': '',
                'email_required': False,
            },
            {
                'name': 'FIDE Rated League',
                'tag': 'demo-fide',
                'description': 'Rated tournament - FIDE ID required',
                'require_name': False,
                'require_personal_email': False,
                'require_gender': False,
                'require_date_of_birth': False,
                'require_nationality': False,
                'require_corporate_email': False,
                'require_contact_number': False,
                'require_fide_id': True,
                'require_regional_rating': False,
                'regional_rating_name': '',
                'organisation_label': '',
                'email_required': True,
            },
            {
                'name': 'Corporate Championship',
                'tag': 'demo-corporate',
                'description': 'Corporate tournament - full info required',
                'require_name': True,
                'require_personal_email': True,
                'require_gender': True,
                'require_date_of_birth': True,
                'require_nationality': True,
                'require_corporate_email': True,
                'require_contact_number': True,
                'require_fide_id': True,
                'require_regional_rating': False,
                'regional_rating_name': '',
                'organisation_label': 'Company',
                'email_required': True,
            },
            {
                'name': 'Community League',
                'tag': 'demo-community',
                'description': 'Community tournament - names only',
                'require_name': True,
                'require_personal_email': False,
                'require_gender': False,
                'require_date_of_birth': False,
                'require_nationality': False,
                'require_corporate_email': False,
                'require_contact_number': False,
                'require_fide_id': False,
                'require_regional_rating': False,
                'regional_rating_name': '',
                'organisation_label': '',
                'email_required': True,
            },
            {
                'name': 'USCF Regional League',
                'tag': 'demo-uscf',
                'description': 'US tournament - USCF rating required',
                'require_name': True,
                'require_personal_email': False,
                'require_gender': False,
                'require_date_of_birth': False,
                'require_nationality': False,
                'require_corporate_email': False,
                'require_contact_number': False,
                'require_fide_id': False,
                'require_regional_rating': True,
                'regional_rating_name': 'USCF',
                'organisation_label': '',
                'email_required': True,
            },
        ]

        for demo in demos:
            league, created = League.objects.update_or_create(
                tag=demo['tag'],
                defaults={
                    'name': demo['name'],
                    'description': demo['description'],
                    'theme': 'blue',
                    'time_control': '45+45',
                    'rating_type': 'classical',
                    'competitor_type': 'team',
                    'pairing_type': 'swiss',
                    'require_name': demo['require_name'],
                    'require_personal_email': demo['require_personal_email'],
                    'require_gender': demo['require_gender'],
                    'require_date_of_birth': demo['require_date_of_birth'],
                    'require_nationality': demo['require_nationality'],
                    'require_corporate_email': demo['require_corporate_email'],
                    'require_contact_number': demo['require_contact_number'],
                    'require_fide_id': demo['require_fide_id'],
                    'require_regional_rating': demo['require_regional_rating'],
                    'regional_rating_name': demo['regional_rating_name'],
                    'organisation_label': demo['organisation_label'],
                    'email_required': demo['email_required'],
                    'show_provisional_warning': False,
                    'ask_availability': False,
                    'is_active': True,
                }
            )

            Season.objects.update_or_create(
                league=league,
                tag=f'{demo["tag"]}-s1',
                defaults={
                    'name': f'{demo["name"]} S1',
                    'rounds': 8,
                    'boards': 4,
                    'start_date': timezone.now() + timedelta(days=30),
                    'registration_open': True,
                    'round_duration': timedelta(days=7),
                }
            )

            self.stdout.write(self.style.SUCCESS(
                f'{"Created" if created else "Updated"}: {league.name}'
            ))
