from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.users.models import User

DEPLOY_MIN_PASSWORD_LENGTH = 12


class Command(BaseCommand):
    help = (
        "Create or reset the demo staff user from DEMO_STAFF_EMAIL. DEBUG only, unless "
        "--deploy, which only creates it, and only while SEED_DEMO_DATA is true."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--deploy",
            action="store_true",
            help="Create the user if absent when SEED_DEMO_DATA is true; never reset it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["deploy"]:
            self._deploy()
            return

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

    def _deploy(self) -> None:
        if not settings.SEED_DEMO_DATA:
            self.stdout.write("SEED_DEMO_DATA is false; no staff user seeded.")
            return

        # This login is reachable from the internet, unlike the DEBUG one.
        if len(settings.DEMO_STAFF_PASSWORD) < DEPLOY_MIN_PASSWORD_LENGTH:
            raise CommandError(
                f"DEMO_STAFF_PASSWORD must be at least {DEPLOY_MIN_PASSWORD_LENGTH} characters."
            )

        # A password staff have since changed must survive every later deploy.
        if User.objects.filter(email__iexact=settings.DEMO_STAFF_EMAIL).exists():
            self.stdout.write("The demo staff user already exists; left unchanged.")
            return

        user = User.objects.create_user(
            email=settings.DEMO_STAFF_EMAIL,
            password=settings.DEMO_STAFF_PASSWORD,
            is_staff=True,
            first_name="Asha",
            last_name="Rai",
        )
        self.stdout.write(self.style.SUCCESS(f"Created staff user {user.email}."))
