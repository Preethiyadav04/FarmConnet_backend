from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import Notification
from .serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    User Notifications ViewSet.
    - Strictly isolates notifications to the authenticated user.
    - Provides fast unread counters, single mark-as-read, and bulk mark-all-read.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()

        qs = Notification.objects.filter(recipient=user).order_by('-created_at')

        unread_only = self.request.query_params.get('unread_only') or self.request.query_params.get('is_read')
        if unread_only in ['true', 'True', '1', 'false', 'False', '0']:
            is_read_bool = unread_only not in ['true', 'True', '1', 'false'] if unread_only in ['false', 'False', '0'] else False
            if self.request.query_params.get('unread_only') in ['true', 'True', '1']:
                qs = qs.filter(is_read=False)
            elif self.request.query_params.get('is_read') is not None:
                is_read_flag = self.request.query_params.get('is_read') in ['true', 'True', '1']
                qs = qs.filter(is_read=is_read_flag)

        notif_type = self.request.query_params.get('type')
        if notif_type:
            qs = qs.filter(notification_type=notif_type)

        return qs

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read."""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read', 'updated_at'])
        return Response({"id": notification.id, "is_read": True, "message": "Notification marked as read."})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all unread notifications for current user as read."""
        updated_count = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({
            "marked_count": updated_count,
            "message": f"Successfully marked {updated_count} notifications as read."
        })

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Returns the count of unread notifications for badge display."""
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({"unread_count": count})
