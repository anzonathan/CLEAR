"""User serializers for CLEAR."""

from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'role', 'gender', 'image', 'email_verified', 'created_at']
        read_only_fields = ['id', 'email', 'role', 'email_verified', 'created_at']


class CustomRegisterSerializer(RegisterSerializer):
    """Custom registration serializer with additional fields."""

    username = None
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    gender = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data['name'] = self.validated_data.get('name', '')
        data['gender'] = self.validated_data.get('gender', '')
        return data

    def save(self, request):
        user = super().save(request)
        user.name = self.cleaned_data.get('name', '')
        user.gender = self.cleaned_data.get('gender', '')
        user.save()
        return user


class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer for admin user management."""

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'role', 'gender', 'image', 'email_verified', 'created_at', 'is_active']


class UpdateRoleSerializer(serializers.Serializer):
    """Serializer for updating user role."""

    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)
