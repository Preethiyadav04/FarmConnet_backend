from rest_framework import permissions


class IsReviewAuthorOrReadOnly(permissions.BasePermission):
    """
    Allows public or authenticated users to read reviews.
    Restricts review modification and deletion strictly to the review author or admin.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, 'is_admin_user', False) or user.is_staff or user.is_superuser:
            return True
        return obj.buyer == user
