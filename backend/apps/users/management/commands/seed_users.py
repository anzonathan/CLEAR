"""Management command to seed initial admin and developer users."""

from django.core.management.base import BaseCommand
from apps.users.models import User


class Command(BaseCommand):
    help = 'Create initial admin and developer accounts'

    def handle(self, *args, **options):
        users = [
            {
                'email': 'admin@clear.local',
                'password': 'admin123',
                'name': 'Admin User',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'dev@clear.local',
                'password': 'dev123',
                'name': 'Developer User',
                'role': 'developer',
                'is_staff': True,
            },
            {
                'email': 'user@clear.local',
                'password': 'user123',
                'name': 'Test User',
                'role': 'user',
            },
        ]

        for user_data in users:
            email = user_data['email']
            password = user_data.pop('password')

            user, created = User.objects.get_or_create(
                email=email,
                defaults=user_data
            )

            if created:
                user.set_password(password)
                user.email_verified = True
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Created {user.role}: {email} (password: {password})')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User already exists: {email}')
                )

        self.stdout.write(self.style.SUCCESS('\nDone! You can now log in with these accounts.'))
