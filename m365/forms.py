from django import forms
from .models import M365Config


class M365ConfigForm(forms.ModelForm):
    class Meta:
        model = M365Config
        fields = ['tenant_id', 'client_id', 'client_secret', 'sharepoint_hostname', 'timesheet_site_path', 'timesheet_list_name']
        widgets = {
            'client_secret': forms.PasswordInput(render_value=True),
        }


