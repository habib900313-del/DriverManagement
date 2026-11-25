from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .activity import log_activity
from .models import ActivityLog, UserPasswordChangeAudit


User = get_user_model()


class ProtectedUserChangeForm(UserChangeForm):
    def clean(self):
        cleaned_data = super().clean()
        user = self.instance
        if not user.pk:
            return cleaned_data

        removes_privilege = any(
            getattr(user, field) and not cleaned_data.get(field, getattr(user, field))
            for field in ("is_active", "is_staff", "is_superuser")
        )
        if user.is_active and user.is_superuser and removes_privilege:
            active_superuser_ids = list(
                User.objects.select_for_update()
                .filter(is_active=True, is_superuser=True)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            if active_superuser_ids == [user.pk]:
                raise ValidationError(
                    "The last active superuser cannot be deactivated or demoted."
                )
        return cleaned_data


class ProtectedUserAdmin(UserAdmin):
    form = ProtectedUserChangeForm

    def user_change_password(self, request, id, form_url=""):
        with transaction.atomic():
            user = self.get_object(request, id)
            if user is not None:
                user = User.objects.select_for_update().get(pk=user.pk)
            previous_password_hash = user.password if user is not None else None

            response = super().user_change_password(request, id, form_url)

            if request.method == "POST" and user is not None:
                user.refresh_from_db()
                if user.password != previous_password_hash:
                    UserPasswordChangeAudit.objects.create(
                        actor=request.user,
                        actor_username=request.user.get_username(),
                        target=user,
                        target_username=user.get_username(),
                    )
                    log_activity(
                        actor=request.user,
                        action="user_admin_password_change",
                        module=ActivityLog.Module.AUTH,
                        description=(
                            "User password changed through Django admin."
                        ),
                        target_type="user",
                        target_id=user.pk,
                        target_label=user.get_username(),
                        metadata={"source": "django_admin"},
                    )
            return response

    @staticmethod
    def _active_superuser_ids():
        return list(
            User.objects.select_for_update()
            .filter(is_active=True, is_superuser=True)
            .order_by("pk")
            .values_list("pk", flat=True)
        )

    def has_delete_permission(self, request, obj=None):
        if (
            obj
            and obj.is_active
            and obj.is_superuser
            and not User.objects.filter(
                is_active=True, is_superuser=True
            )
            .exclude(pk=obj.pk)
            .exists()
        ):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        before_data = None
        if change:
            before_data = {
                field: form.initial.get(field)
                for field in ("username", "is_active", "is_staff", "is_superuser")
            }
        super().save_model(request, obj, form, change)
        log_activity(
            actor=request.user,
            action="user_admin_update" if change else "user_admin_create",
            module=ActivityLog.Module.USERS,
            description="User account changed through Django admin.",
            target_type="user",
            target_id=obj.pk,
            target_label=obj.get_username(),
            before_data=before_data,
            after_data={
                field: getattr(obj, field)
                for field in ("username", "is_active", "is_staff", "is_superuser")
            },
        )

    def delete_model(self, request, obj):
        with transaction.atomic():
            active_superuser_ids = self._active_superuser_ids()
            if active_superuser_ids == [obj.pk]:
                raise PermissionDenied(
                    "The last active superuser cannot be deleted."
                )
            username = obj.get_username()
            log_activity(
                actor=request.user,
                action="user_admin_delete",
                module=ActivityLog.Module.USERS,
                description="User account deleted through Django admin.",
                target_type="user",
                target_id=obj.pk,
                target_label=username,
            )
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            active_superuser_ids = set(self._active_superuser_ids())
            selected_active_superuser_ids = set(
                queryset.filter(pk__in=active_superuser_ids).values_list(
                    "pk", flat=True
                )
            )
            if active_superuser_ids and active_superuser_ids.issubset(
                selected_active_superuser_ids
            ):
                raise PermissionDenied(
                    "The last active superuser cannot be deleted."
                )
            deleted_users = list(queryset)
            for user in deleted_users:
                log_activity(
                    actor=request.user,
                    action="user_admin_delete",
                    module=ActivityLog.Module.USERS,
                    description="User account deleted through Django admin.",
                    target_type="user",
                    target_id=user.pk,
                    target_label=user.get_username(),
                )
            super().delete_queryset(request, queryset)
