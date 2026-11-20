from rest_framework import permissions


class IsFarmer(permissions.BasePermission):
    """Allows access only to authenticated users with the Farmer role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'is_farmer', False)
        )


class IsBuyer(permissions.BasePermission):
    """Allows access only to authenticated users with the Buyer role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'is_buyer', False)
        )


class IsTransporter(permissions.BasePermission):
    """Allows access only to authenticated users with the Transporter role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'is_transporter', False)
        )


class IsAdminRole(permissions.BasePermission):
    """Allows access only to Admin users or superusers."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'is_admin_user', False)
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Object-level permission allowing only the owner to edit or delete."""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = getattr(obj, 'user', getattr(obj, 'farmer', None))
        return user == request.user or request.user.is_superuser
