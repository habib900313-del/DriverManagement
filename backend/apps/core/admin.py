from django.contrib import admin


class SuperuserAdminSite(admin.AdminSite):
    def has_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_superuser)
