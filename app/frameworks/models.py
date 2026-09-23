from django.db import models
from simple_history.models import HistoricalRecords


class Framework(models.Model):
    name = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} {self.version}".strip()


class FrameworkControl(models.Model):
    framework = models.ForeignKey(
        Framework, on_delete=models.CASCADE, related_name='controls'
    )
    code = models.CharField(max_length=50)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = ('framework', 'code')
        ordering = ['framework', 'code']

    def __str__(self):
        return f"{self.framework.name} {self.code}"