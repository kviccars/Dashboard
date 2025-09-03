from django.db import models


class M365Config(models.Model):
    tenant_id = models.CharField(max_length=64)
    client_id = models.CharField(max_length=64)
    client_secret = models.CharField(max_length=256)
    sharepoint_hostname = models.CharField(
        max_length=255,
        blank=True,
        help_text="e.g., contoso.sharepoint.com"
    )
    timesheet_site_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Site path for the timesheet list, e.g., /sites/TeamA"
    )
    timesheet_list_name = models.CharField(
        max_length=255,
        default='timesheet',
        help_text="Display name of the timesheet list"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Microsoft 365 Configuration'
        verbose_name_plural = 'Microsoft 365 Configuration'

    def __str__(self) -> str:
        return f"M365Config(tenant={self.tenant_id}, client={self.client_id})"


