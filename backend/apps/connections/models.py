"""Connection models for CLEAR."""

import secrets
import string
from django.db import models
from django.utils import timezone
from datetime import timedelta


def generate_id():
    """Generate a nanoid-like ID."""
    return secrets.token_urlsafe(16)[:21]


def generate_pair_code():
    """Generate a 6-character alphanumeric pair code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(6))


def default_expiry():
    """Return expiry time 10 minutes from now."""
    return timezone.now() + timedelta(minutes=10)


class PairCode(models.Model):
    """Pair code for connecting two users."""

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    code = models.CharField(max_length=6, default=generate_pair_code, unique=True)
    creator = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='created_pair_codes'
    )
    expires_at = models.DateTimeField(default=default_expiry)
    used = models.BooleanField(default=False)
    used_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_pair_codes'
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pair_codes'
        verbose_name = 'Pair Code'
        verbose_name_plural = 'Pair Codes'

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        """Check if the pair code is valid (not used and not expired)."""
        return not self.used and timezone.now() < self.expires_at


class Connection(models.Model):
    """Connection between two users."""

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    user_a = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connections_as_a'
    )
    user_b = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connections_as_b'
    )
    pair_code = models.ForeignKey(
        PairCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'connections'
        verbose_name = 'Connection'
        verbose_name_plural = 'Connections'
        constraints = [
            models.UniqueConstraint(
                fields=['user_a', 'user_b'],
                name='unique_connection'
            )
        ]

    def __str__(self):
        return f'{self.user_a.email} <-> {self.user_b.email}'

    def get_other_user(self, user):
        """Get the other user in the connection."""
        if self.user_a_id == user.id:
            return self.user_b
        return self.user_a
