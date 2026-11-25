import getpass
import sys

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.activity import log_activity
from apps.core.models import ActivityLog, UserPasswordChangeAudit


def _has_interactive_terminal():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        isatty = getattr(stream, "isatty", None)
        if not callable(isatty):
            return False
        try:
            if not isatty():
                return False
        except (OSError, ValueError):
            return False
    return True


class Command(BaseCommand):
    help = "Interactively reset the password of an active Django superuser."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username of the superuser to recover")

    def handle(self, *args, **options):
        if not _has_interactive_terminal():
            raise CommandError(
                "This command requires an interactive terminal; stdin, stdout, "
                "and stderr must be connected to a terminal."
            )

        User = get_user_model()
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError("No account exists with that username.") from exc

        if not (user.is_active and user.is_staff and user.is_superuser):
            raise CommandError(
                "The target must be an active account with both staff and "
                "superuser privileges."
            )

        self.stdout.write(
            f"Target account: {user.get_username()} "
            "(active staff superuser)"
        )
        if input("Type the username to confirm: ") != user.get_username():
            raise CommandError("Username confirmation did not match; no changes made.")

        password = getpass.getpass("New password: ")
        password_confirmation = getpass.getpass("Confirm new password: ")
        if not password or password != password_confirmation:
            raise CommandError("Passwords must be non-empty and match.")

        try:
            password_validation.validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(
                "Password rejected by the configured Django validators."
            ) from exc

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            if (
                user.get_username() != username
                or not (user.is_active and user.is_staff and user.is_superuser)
            ):
                raise CommandError(
                    "The confirmed account is no longer the same active staff "
                    "superuser; "
                    "no changes made."
                )

            try:
                password_validation.validate_password(password, user=user)
            except ValidationError as exc:
                raise CommandError(
                    "Password rejected by the configured Django validators."
                ) from exc
            user.set_password(password)
            user.save(update_fields=["password"])

            UserPasswordChangeAudit.objects.create(
                actor=None,
                actor_username="management-command",
                target=user,
                target_username=user.get_username(),
            )
            log_activity(
                action="superuser_password_recovery",
                module=ActivityLog.Module.AUTH,
                description="Superuser password reset through a management command.",
                target_type="user",
                target_id=user.pk,
                target_label=user.get_username(),
                metadata={"source": "management_command"},
            )

        self.stdout.write(self.style.SUCCESS("Superuser password updated."))
