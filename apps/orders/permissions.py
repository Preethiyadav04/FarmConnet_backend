from rest_framework import permissions


class IsOrderParticipant(permissions.BasePermission):
    """
    Ensures only the buyer who placed the order, the farmer who fulfills it,
    or a platform admin can view or interact with the order.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if getattr(request.user, 'is_admin_user', False) or request.user.is_staff or request.user.is_superuser:
            return True
        return obj.buyer == request.user or obj.farmer == request.user


class IsNegotiationParticipant(permissions.BasePermission):
    """
    Ensures only the buyer who initiated the offer or the farmer who owns
    the crop listing (or admin) can view or respond to a negotiation.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if getattr(request.user, 'is_admin_user', False) or request.user.is_staff or request.user.is_superuser:
            return True
        return obj.buyer == request.user or obj.listing.farmer == request.user
