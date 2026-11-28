from django import forms

from .models import Asset


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = [
            # Identification
            'name', 'hostname', 'ip_address', 'fqdn',
            # Classification
            'asset_type', 'hosting', 'cloud_provider', 'cloud_region',
            'location', 'os_family', 'os_version',
            # Business context
            'vendor', 'classification', 'environment',
            # Ownership
            'owner_dept', 'owner_user', 'is_active',
            # Operational context
            'depends_on',
            # Business continuity (BIA)
            'rto_hours', 'rpo_hours', 'mtpd_hours',
            'bcp_policy', 'drp_policy', 'last_continuity_test',
            # Risk ratings
            'criticality', 'confidentiality', 'integrity', 'availability', 'value',
            # Governance
            'policies', 'category',
            # Description
            'description',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe what this asset is, what it does, and where it lives.'}),
            'value': forms.NumberInput(attrs={'step': '0.01'}),
            'last_continuity_test': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'name':          'Short, recognizable name (e.g. "Web Application Server").',
            'hostname':      'DNS or system hostname (e.g. web-prod-01.corp.local).',
            'ip_address':    'Primary IPv4 or IPv6 address.',
            'fqdn':          'Fully qualified domain name.',
            'asset_type':    'Category of asset.',
            'hosting':       'Where this asset is hosted.',
            'cloud_provider':'Which cloud provider hosts this asset.',
            'cloud_region':  'Cloud region or availability zone (e.g. us-east-1).',
            'location':      'Physical location or country.',
            'os_family':     'Operating system family.',
            'os_version':    'Specific OS version.',
            'vendor':        'Primary vendor that supplies, hosts, or supports this asset.',
            'classification':'Data classification level.',
            'environment':   'Deployment environment.',
            'owner_dept':    'Department responsible for this asset.',
            'owner_user':    'Individual responsible for this asset (optional).',
            'criticality':   'Business criticality — drives risk scoring.',
            'confidentiality':'CIA rating for confidentiality.',
            'integrity':     'CIA rating for integrity.',
            'availability':  'CIA rating for availability.',
            'value':         'Estimated monetary value (for risk quantification).',
            'policies':      'Policies that govern this asset. Hold Ctrl (Cmd on Mac) to select multiple.',
            'category':      'Legacy category — prefer asset_type above.',
            'description':   'Required — at least 20 characters.',
            'rto_hours':     'Hours the business can tolerate this asset being down.',
            'rpo_hours':     'Hours of data loss the business can tolerate.',
            'mtpd_hours':    'Longest outage before the impact becomes unacceptable.',
            'bcp_policy':    'Business continuity plan that covers this asset.',
            'drp_policy':    'Disaster recovery plan that covers this asset.',
            'last_continuity_test': 'Last failover, restore or DR drill. Older than 12 months counts as stale.',
        }

    def clean_description(self):
        desc = (self.cleaned_data.get('description') or '').strip()
        if len(desc) < 20:
            raise forms.ValidationError('Description must be at least 20 characters.')
        return desc

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if len(name) < 3:
            raise forms.ValidationError('Asset name must be at least 3 characters.')
        return name
