from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0002_streamsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='segments',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
