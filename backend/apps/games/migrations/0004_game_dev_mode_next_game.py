import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0003_game_segments'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='dev_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='game',
            name='next_game',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to='games.game',
            ),
        ),
    ]
