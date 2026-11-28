from django import forms
from django.utils import timezone

from .models import Vulnerability, Finding


class ManualVulnerabilityForm(forms.Form):
    """
    Combined manual entry: creates a Vulnerability record + a Finding on an asset.
    """
    # ---- Vulnerability fields ----
    title = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Hardcoded credentials in deployment script'}),
        help_text='Short name for the vulnerability'
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'What is the issue? Where was it found? How was it discovered?'})
    )
    cve_id = forms.CharField(
        max_length=50, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'CVE-2024-XXXXX (leave blank for non-CVE findings)'})
    )
    cvss_score = forms.DecimalField(
        max_digits=3, decimal_places=1, min_value=0, max_value=10,
        initial=5.0
    )
    cvss_severity = forms.ChoiceField(
        choices=Vulnerability.SEVERITY_CHOICES, initial='medium'
    )

    # ---- Finding fields ----
    asset = forms.ModelChoiceField(queryset=None)
    port = forms.CharField(max_length=20, required=False)
    evidence = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Scanner output, exploit proof, manual observation, etc.'})
    )

    assigned_to = forms.ModelChoiceField(queryset=None, required=False)
    assigned_team = forms.ModelChoiceField(queryset=None, required=False)

    status = forms.ChoiceField(choices=Finding.STATUS_CHOICES, initial='new')
    discovered_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}), initial=timezone.now().date
    )
    sla_due_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Leave blank to auto-compute from severity (Critical=7d, High=30d, Medium=90d, Low=180d).'
    )
    solution = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'How should this be fixed?'})
    )
    remediation_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from assets.models import Asset
        from core.models import Department, real_users

        self.fields['asset'].queryset = Asset.objects.filter(is_active=True).order_by('asset_id')
        self.fields['assigned_to'].queryset = real_users().filter(is_active=True).order_by('username')
        self.fields['assigned_team'].queryset = Department.objects.all().order_by('name')

    def clean(self):
        cleaned = super().clean()
        cve_id = (cleaned.get('cve_id') or '').strip()
        if cve_id:
            # Check for existing CVE
            existing = Vulnerability.objects.filter(cve_id__iexact=cve_id).first()
            if existing:
                cleaned['existing_vulnerability'] = existing
        return cleaned


class ScannerImportForm(forms.Form):
    """Upload a CSV or JSON scanner output to create/update Findings."""

    file = forms.FileField(
        label='Scanner export (.csv or .json)',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.json',
        }),
        help_text='Max 5 MB. Supports CSV (Nessus/OpenVAS/Qualys/generic) and JSON (flat list, Trivy, SARIF 2.1.0).',
    )
    default_asset = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='Fallback asset (optional)',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Used when a scanner row does not specify a host, IP, FQDN, or asset ID.',
    )
    scanner_label = forms.CharField(
        max_length=80,
        required=False,
        label='Scanner name (optional)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. OpenVAS, Nessus, Trivy',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from assets.models import Asset
        from core.mixins import writable_queryset

        qs = Asset.objects.filter(is_active=True)
        if user is not None:
            qs = writable_queryset(qs, user)
        else:
            qs = qs.none()
        self.fields['default_asset'].queryset = qs.order_by('asset_id')

