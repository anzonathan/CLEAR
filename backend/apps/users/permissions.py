"""Custom permissions for CLEAR."""

from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Permission class for admin users."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsAdminOrDeveloper(BasePermission):
    """Permission class for admin or developer users."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'developer')
