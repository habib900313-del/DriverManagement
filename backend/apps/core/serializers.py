from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import ActivityLog


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        trim_whitespace=True,
        error_messages={
            "required": "نام کاربری الزامی است.",
            "blank": "نام کاربری نمی‌تواند خالی باشد.",
        },
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        trim_whitespace=False,
        error_messages={
            "required": "رمز عبور الزامی است.",
            "blank": "رمز عبور نمی‌تواند خالی باشد.",
        },
    )


class ManagedUserCreateSerializer(serializers.Serializer):
    """Input accepted by the superuser-only user-management endpoint.

    The API deliberately exposes roles rather than Django's privilege flags,
    so a request cannot promote a new account to superuser status.
    """

    username = serializers.CharField(max_length=150, trim_whitespace=True)
    full_name = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirmation = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=("admin", "guest"))

    def to_internal_value(self, data):
        unknown_fields = set(data) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {
                    field: ["این فیلد قابل تنظیم نیست."]
                    for field in sorted(unknown_fields)
                }
            )
        return super().to_internal_value(data)

    def validate_username(self, username):
        if get_user_model().objects.filter(username=username).exists():
            raise serializers.ValidationError("این نام کاربری قبلاً استفاده شده است.")
        return username

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({"password_confirmation": "رمزهای عبور یکسان نیستند."})
        user = get_user_model()(username=attrs["username"])
        name_parts = attrs["full_name"].split(None, 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class ManagedUserUpdateSerializer(serializers.Serializer):
    """Editable fields for non-superuser accounts."""

    full_name = serializers.CharField(max_length=150, required=False)
    role = serializers.ChoiceField(choices=("admin", "guest"), required=False)
    is_active = serializers.BooleanField(required=False)

    def to_internal_value(self, data):
        unknown_fields = set(data) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {
                    field: ["این فیلد قابل ویرایش نیست."]
                    for field in sorted(unknown_fields)
                }
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("حداقل یک فیلد برای ویرایش لازم است.")
        return attrs


class ManagedUserPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    password_confirmation = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def to_internal_value(self, data):
        unknown_fields = set(data) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {
                    field: ["این فیلد قابل تنظیم نیست."]
                    for field in sorted(unknown_fields)
                }
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError(
                {"password_confirmation": "رمزهای عبور یکسان نیستند."}
            )
        try:
            validate_password(attrs["new_password"], user=self.context["user"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class ActivityLogSerializer(serializers.ModelSerializer):
    """Read-only representation for the activity-log list."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "timestamp",
            "actor_username",
            "action",
            "module",
            "description",
            "target_type",
            "target_id",
            "target_label",
            "status",
            "status_label",
            "ip_address",
        ]
        read_only_fields = fields


class ActivityLogDetailSerializer(ActivityLogSerializer):
    """List fields plus the payloads needed for the comparison view."""

    class Meta(ActivityLogSerializer.Meta):
        fields = ActivityLogSerializer.Meta.fields + [
            "metadata",
            "before_data",
            "after_data",
        ]
        read_only_fields = fields
