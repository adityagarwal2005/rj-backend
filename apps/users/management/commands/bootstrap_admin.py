from django.conf import settings
from django.core.management.base import BaseCommand

from apps.users.models import Role, User


class Command(BaseCommand):
    """
    Creates/resets one superuser from ADMIN_EMAIL + ADMIN_PASSWORD env vars.

    Exists so a shell-less Render free-tier instance can still get (or
    recover) an admin login: the build command runs this on every deploy,
    and it's a silent no-op whenever those two env vars aren't set - so
    it's safe to leave wired into the build step permanently. The actual
    email/password are chosen and typed by the store owner directly into
    Render's Environment tab - this command never sees or stores them
    anywhere except as an argon2/pbkdf2 hash on the User row, same as any
    other password set through Django.
    """

    help = "Idempotently create or reset the admin user named by ADMIN_EMAIL/ADMIN_PASSWORD env vars."

    def handle(self, *args, **options):
        email = getattr(settings, "ADMIN_EMAIL", "")
        password = getattr(settings, "ADMIN_PASSWORD", "")

        if not email or not password:
            self.stdout.write("ADMIN_EMAIL/ADMIN_PASSWORD not set - skipping.")
            return

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"full_name": "Admin", "role": Role.ADMIN, "is_staff": True, "is_superuser": True},
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        verb = "Created" if created else "Reset password for"
        self.stdout.write(self.style.SUCCESS(f"{verb} admin user {email}."))
