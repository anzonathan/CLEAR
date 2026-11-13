from django.apps import AppConfig


class FieldConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.field'
    verbose_name = 'Field (CV/ML)'
