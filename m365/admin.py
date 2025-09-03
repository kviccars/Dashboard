from django.contrib import admin
from .models import M365Config


@admin.register(M365Config)
class M365ConfigAdmin(admin.ModelAdmin):
    list_display = ('tenant_id', 'client_id', 'created_at', 'updated_at')


