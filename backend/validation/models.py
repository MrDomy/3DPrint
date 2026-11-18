from django.db import models

from config.base import BaseModel


class ValidationResult(BaseModel):
    class Verdict(models.TextChoices):
        OK = 'OK', 'Без замечаний'
        WARNING = 'WARNING', 'Есть предупреждения'
        ERROR = 'ERROR', 'Есть ошибки'

    model_version = models.ForeignKey('models_app.ModelVersion', on_delete=models.CASCADE,
                                      related_name='validation_results')
    verdict = models.CharField(max_length=8, choices=Verdict.choices)
    issues = models.JSONField(default=list)
    needs_support = models.BooleanField(default=False)

    class Meta:
        db_table = 'validation_result'
        ordering = ['-created_at']
