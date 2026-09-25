from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.users.models import User


class Command(BaseCommand):
    help = "Create or reset the demo staff user from DEMO_STAFF_EMAIL. DEBUG only."

    def handle(self, *args: Any, **options: Any) -> None:
        # A known password on a staff account must never reach a real deployment.
        if not settings.DEBUG:
            raise CommandError("seed_staff creates a known staff login and only runs with DEBUG.")

        user, created = User.objects.update_or_create(
            email=settings.DEMO_STAFF_EMAIL,
            defaults={
                "is_staff": True,
                "is_active": True,
                "first_name": "Asha",
                "last_name": "Rai",
            },
        )
        user.set_password(settings.DEMO_STAFF_PASSWORD)
        user.save(update_fields=["password"])

        verb = "Created" if created else "Reset"
        self.stdout.write(self.style.SUCCESS(f"{verb} staff user {user.email}."))
