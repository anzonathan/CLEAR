"""Custom adapters for allauth."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for email-based auth."""

    def save_user(self, request, user, form, commit=True):
        """Save user with custom fields."""
        user = super().save_user(request, user, form, commit=False)
        data = form.cleaned_data
        user.name = data.get('name', '')
        user.gender = data.get('gender', '')
        if commit:
            user.save()
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter."""

    def populate_user(self, request, sociallogin, data):
        """Populate user from social login data."""
        user = super().populate_user(request, sociallogin, data)
        user.name = data.get('name', '')
        if sociallogin.account.provider == 'google':
            extra_data = sociallogin.account.extra_data
            user.image = extra_data.get('picture', '')
        return user
