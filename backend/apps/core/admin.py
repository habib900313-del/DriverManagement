from django.contrib.admin import AdminSite


class SuperuserAdminSite(AdminSite):
    def has_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and user.is_superuser)
