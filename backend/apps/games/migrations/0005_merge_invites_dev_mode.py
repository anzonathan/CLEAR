from django.db import migrations


class Migration(migrations.Migration):
    """Merge the game-invites branch with the segments / dev-mode branch."""

    dependencies = [
        ('games', '0003_game_invites'),
        ('games', '0004_game_dev_mode_next_game'),
    ]

    operations = []
