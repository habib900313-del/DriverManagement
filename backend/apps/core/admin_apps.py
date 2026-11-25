from django.contrib.admin.apps import AdminConfig


class SuperuserOnlyAdminConfig(AdminConfig):
    default_site = "apps.core.admin.SuperuserAdminSite"

    def ready(self):
        super().ready()

        from django.contrib import admin
        from django.contrib.auth import get_user_model

        from .user_admin import ProtectedUserAdmin

        user_model = get_user_model()
        if admin.site.is_registered(user_model):
            admin.site.unregister(user_model)
        admin.site.register(user_model, ProtectedUserAdmin)
