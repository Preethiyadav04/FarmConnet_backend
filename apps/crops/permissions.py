from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allows public or authenticated read access.
    Write operations (POST, PUT, DELETE) are strictly restricted to Admin users.
    Used for Categories and Mandi Market Prices.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            (getattr(request.user, 'is_admin_user', False) or request.user.is_staff or request.user.is_superuser)
        )


class IsFarmerOwnerOrReadOnly(permissions.BasePermission):
    """
    Public / buyers can view crop details.
    Only registered Farmers can create crops.
    Only the specific Farmer who owns the crop (or Admin) can update or delete it.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'is_farmer', False)
        )

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            (obj.farmer == request.user or getattr(request.user, 'is_admin_user', False) or request.user.is_superuser)
        )
