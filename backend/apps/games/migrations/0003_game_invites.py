import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0002_streamsettings'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='proposed_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='game',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'), ('declined', 'Declined'), ('scheduled', 'Scheduled'),
                    ('live', 'Live'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
                ],
                default='pending', max_length=12,
            ),
        ),
    ]
