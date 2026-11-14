from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


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
