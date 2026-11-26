import apps.games.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0005_merge_invites_dev_mode'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DatasetExport',
            fields=[
                ('id', models.CharField(default=apps.games.models.generate_id, max_length=32, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=120)),
                ('clips', models.JSONField(default=list)),
                ('options', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed')], default='queued', max_length=10)),
                ('progress', models.CharField(blank=True, max_length=200)),
                ('error', models.TextField(blank=True)),
                ('result', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'dataset_exports', 'ordering': ['-created_at']},
        ),
    ]
