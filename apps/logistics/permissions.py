from rest_framework import permissions


class IsTransporter(permissions.BasePermission):
    """Allows access only to authenticated users with the Transporter role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (getattr(request.user, 'is_transporter', False) or getattr(request.user, 'is_admin_user', False))
        )


class IsLogisticsParticipant(permissions.BasePermission):
    """
    Allows tracking access to the buyer, farmer, assigned transporter, or admin.
    Status updates are strictly limited to the assigned transporter or admin.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            return True
        # For viewing/tracking: buyer, farmer, or assigned transporter
        is_participant = (
            obj.transporter == user or
            obj.order.buyer == user or
            obj.order.farmer == user or
            obj.requester == user
        )
        if request.method in permissions.SAFE_METHODS:
            return is_participant
        # For updating/modifying: only assigned transporter or admin
        return obj.transporter == user or getattr(user, 'is_admin_user', False)
