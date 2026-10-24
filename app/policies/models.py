from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department


class PolicyCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Policy categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Policy(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('review',    'Under Review'),
        ('approved',  'Approved'),
        ('retired',   'Retired'),
    ]

    title = models.CharField(max_length=300)
    code = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(
        PolicyCategory, on_delete=models.PROTECT, related_name='policies',
        null=True, blank=True
    )
    description = models.TextField(blank=True)
    content = models.TextField(blank=True)
    version = models.CharField(max_length=20, default='1.0')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='policies'
    )
    approved_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_policies'
    )
    approval_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    document = models.FileField(upload_to='policies/', null=True, blank=True)
    applies_to_departments = models.ManyToManyField(
        Department, blank=True, related_name='applicable_policies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_policies', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_policies', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'Policies'

    def __str__(self):
        return f"{self.code} - {self.title}"

    # Workflow (state machine) — enforced in PolicyForm.
    TRANSITIONS = {
        'draft':    {'review', 'retired'},
        'review':   {'draft', 'approved', 'retired'},
        'approved': {'review', 'retired'},
        'retired':  {'draft'},
    }

    def allowed_transitions(self):
        return self.TRANSITIONS.get(self.status, set())

    def can_transition_to(self, new_status):
        return new_status == self.status or new_status in self.allowed_transitions()


class PolicyAttestation(models.Model):
    """A person's signed acknowledgement of one policy version.

    Auditors ask "who has read the password policy, and of which edition?".
    This answers it with a row per (policy, version, user). Re-approval of
    the policy with a bumped version makes those attestations stale — the
    detail page shows *this* version's attestations only.
    """
    policy = models.ForeignKey(
        Policy, on_delete=models.CASCADE, related_name='attestations'
    )
    user = models.ForeignKey(
        'core.User', on_delete=models.CASCADE, related_name='policy_attestations'
    )
    version = models.CharField(
        max_length=20,
        help_text='Snapshot of the policy version at attestation time.'
    )
    attested_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'user', 'version'],
                name='unique_attestation_per_policy_version',
            ),
        ]
        ordering = ['-attested_at']
        verbose_name = 'Policy attestation'
        verbose_name_plural = 'Policy attestations'

    def __str__(self):
        return f'{self.policy.code} v{self.version} - {self.user}'

    def save(self, *args, **kwargs):
        if not self.version:
            self.version = self.policy.version
        super().save(*args, **kwargs)

    @property
    def is_current_version(self):
        return self.version == self.policy.version