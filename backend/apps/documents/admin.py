from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        "document_name",
        "driver",
        "upload_date",
        "status",
        "file_size_mb",
    ]
    list_filter = ["status", "upload_date", "driver"]
    search_fields = ["document_name", "driver__driver_code", "driver__full_name"]
    readonly_fields = ["upload_date", "file_size_mb", "original_filename"]

    fieldsets = (
        (None, {
            "fields": ("driver", "document_name", "file", "status")
        }),
        ("Detalles", {
            "fields": ("original_filename", "file_size_mb", "description", "upload_date"),
            "classes": ("collapse",),
        }),
    )

    def file_size_mb(self, obj):
        """Display file size in MB."""
        if obj.file and hasattr(obj.file, 'size'):
            return f"{obj.file.size / 1024 / 1024:.2f} MB"
        return "—"
    file_size_mb.short_description = "حجم"

    def get_queryset(self, request):
        """Show only active documents by default."""
        return super().get_queryset(request).filter(status='active')
