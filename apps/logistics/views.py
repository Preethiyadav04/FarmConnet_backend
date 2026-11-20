from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q

from .models import TransportRequest, TransportStatus
from .serializers import (
    TransportRequestListSerializer,
    TransportRequestDetailSerializer,
    TransportRequestCreateSerializer,
    TransportStatusUpdateSerializer,
)
from .permissions import IsTransporter, IsLogisticsParticipant
from apps.orders.models import Order, OrderStatus


class LogisticsResultsPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 50


class TransportRequestViewSet(viewsets.ModelViewSet):
    """
    Logistics Transportation Request & Tracking ViewSet.
    - Transporters browse available dispatch jobs and accept them.
    - Assigned transporters update status from 'accepted' -> 'picked_up' -> 'in_transit' -> 'delivered'.
    - Farmers and Buyers monitor shipment status and real-time tracking notes.
    """
    pagination_class = LogisticsResultsPagination
    permission_classes = [permissions.IsAuthenticated, IsLogisticsParticipant]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['order__order_number', 'pickup_city', 'drop_city', 'vehicle_type_needed']
    ordering_fields = ['created_at', 'estimated_cost', 'estimated_distance_km']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return TransportRequestCreateSerializer
        elif self.action in ['retrieve', 'track']:
            return TransportRequestDetailSerializer
        elif self.action == 'update_status':
            return TransportStatusUpdateSerializer
        return TransportRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return TransportRequest.objects.none()

        qs = TransportRequest.objects.select_related('order', 'order__buyer', 'order__farmer', 'requester', 'transporter')

        # Admin can view all logistics
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            return qs

        # Transporter can view jobs assigned to them plus open unassigned requests
        if getattr(user, 'is_transporter', False):
            mode = self.request.query_params.get('mode')
            if mode == 'my_jobs':
                return qs.filter(transporter=user)
            elif mode == 'available':
                return qs.filter(status=TransportStatus.REQUESTED, transporter__isnull=True)
            return qs.filter(Q(transporter=user) | Q(status=TransportStatus.REQUESTED))

        # Farmer sees deliveries for their crops
        if getattr(user, 'is_farmer', False):
            return qs.filter(Q(order__farmer=user) | Q(requester=user))

        # Buyer sees deliveries for their orders
        return qs.filter(Q(order__buyer=user) | Q(requester=user))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        transport = serializer.save()
        return Response(TransportRequestDetailSerializer(transport).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsTransporter])
    def available_jobs(self, request):
        """Browse open transport shipment requests waiting for a driver."""
        qs = TransportRequest.objects.filter(
            status=TransportStatus.REQUESTED,
            transporter__isnull=True
        ).select_related('order', 'order__buyer', 'order__farmer')

        pickup_city = request.query_params.get('pickup_city')
        drop_city = request.query_params.get('drop_city')
        if pickup_city:
            qs = qs.filter(pickup_city__icontains=pickup_city)
        if drop_city:
            qs = qs.filter(drop_city__icontains=drop_city)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = TransportRequestListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TransportRequestListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsTransporter])
    def accept_job(self, request, pk=None):
        """Transporter claims and accepts an available transport request."""
        transport = self.get_object()

        if transport.order.status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            return Response(
                {"detail": f"Cannot claim transport for an order that is {transport.order.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if transport.transporter and transport.transporter != request.user:
            return Response(
                {"detail": "This transport job has already been claimed by another transporter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if transport.status != TransportStatus.REQUESTED:
            return Response(
                {"detail": f"Transport request in status '{transport.status}' cannot be accepted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        transport.transporter = request.user
        transport.status = TransportStatus.ACCEPTED
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
        transport.tracking_notes = f"{transport.tracking_notes}\n[{timestamp}] Job accepted by {request.user.username}".strip()
        transport.save(update_fields=['transporter', 'status', 'tracking_notes', 'updated_at'])

        # Update order status if order was confirmed
        order = transport.order
        if order.status == OrderStatus.CONFIRMED:
            order.status = OrderStatus.PROCESSING
            order.save(update_fields=['status', 'updated_at'])

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=order.buyer,
                title="Transporter Assigned",
                message=f"Transporter {request.user.username} claimed shipping for order #{order.order_number}.",
                notification_type=NotificationType.LOGISTICS,
                action_url=f"/orders/{order.id}"
            )
            send_notification(
                recipient=order.farmer,
                title="Transporter Assigned",
                message=f"Transporter {request.user.username} will pick up produce for order #{order.order_number}.",
                notification_type=NotificationType.LOGISTICS,
                action_url=f"/orders/{order.id}"
            )
        except Exception:
            pass

        return Response({
            "id": transport.id,
            "order_number": transport.order.order_number,
            "status": transport.status,
            "transporter": request.user.username,
            "message": "Transport job accepted successfully!"
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsLogisticsParticipant])
    def update_status(self, request, pk=None):
        """
        Assigned transporter or Admin updates the shipment progress.
        Valid status transitions: accepted -> picked_up -> in_transit -> delivered.
        """
        transport = self.get_object()

        # Only assigned transporter or admin can update status
        if transport.transporter != request.user and not (getattr(request.user, 'is_admin_user', False) or request.user.is_superuser):
            return Response(
                {"detail": "Only the assigned transporter or admin can update transport status."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TransportStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        notes = serializer.validated_data.get('tracking_notes', '')
        final_charge = serializer.validated_data.get('final_charge')

        # Prevent progressing transport on cancelled/rejected orders
        if transport.status == TransportStatus.CANCELLED or transport.order.status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            return Response(
                {"detail": "Cannot advance transport status on a cancelled or rejected order."},
                status=status.HTTP_400_BAD_REQUEST
            )

        VALID_TRANSITIONS = {
            TransportStatus.ACCEPTED: [TransportStatus.PICKED_UP, TransportStatus.CANCELLED],
            TransportStatus.PICKED_UP: [TransportStatus.IN_TRANSIT, TransportStatus.CANCELLED],
            TransportStatus.IN_TRANSIT: [TransportStatus.DELIVERED, TransportStatus.CANCELLED],
            TransportStatus.REQUESTED: [TransportStatus.ACCEPTED, TransportStatus.CANCELLED],
            TransportStatus.DELIVERED: [],
            TransportStatus.CANCELLED: [],
        }
        allowed = VALID_TRANSITIONS.get(transport.status, [])
        if new_status not in allowed and not (getattr(request.user, 'is_admin_user', False) or request.user.is_superuser):
            return Response(
                {"detail": f"Invalid transition from '{transport.status}' to '{new_status}'. Permitted next states: {allowed}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        transport.status = new_status
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')

        if notes:
            transport.tracking_notes = f"{transport.tracking_notes}\n[{timestamp} - {new_status.upper()}]: {notes}".strip()
        else:
            transport.tracking_notes = f"{transport.tracking_notes}\n[{timestamp}]: Status updated to {new_status}".strip()

        if final_charge is not None:
            transport.final_charge = final_charge

        update_fields = ['status', 'tracking_notes', 'updated_at']
        if final_charge is not None:
            update_fields.append('final_charge')

        if new_status == TransportStatus.DELIVERED:
            transport.delivered_at = timezone.now()
            update_fields.append('delivered_at')
            # Also update linked order to delivered
            order = transport.order
            if order.status != OrderStatus.DELIVERED:
                order.status = OrderStatus.DELIVERED
                order.save(update_fields=['status', 'updated_at'])

        elif new_status == TransportStatus.PICKED_UP:
            order = transport.order
            if order.status in [OrderStatus.CONFIRMED, OrderStatus.PROCESSING]:
                order.status = OrderStatus.DISPATCHED
                order.save(update_fields=['status', 'updated_at'])

        elif new_status == TransportStatus.IN_TRANSIT:
            order = transport.order
            if order.status != OrderStatus.DISPATCHED:
                order.status = OrderStatus.DISPATCHED
                order.save(update_fields=['status', 'updated_at'])

        transport.save(update_fields=update_fields)

        try:
            from apps.notifications.models import send_notification, NotificationType
            status_label = transport.get_status_display()
            send_notification(
                recipient=transport.order.buyer,
                title=f"Shipment Update: {status_label}",
                message=f"Order #{transport.order.order_number} shipment is now '{status_label}'. Notes: {notes or 'No additional notes'}",
                notification_type=NotificationType.LOGISTICS,
                action_url=f"/orders/{transport.order.id}"
            )
            send_notification(
                recipient=transport.order.farmer,
                title=f"Shipment Update: {status_label}",
                message=f"Order #{transport.order.order_number} shipment is now '{status_label}'. Notes: {notes or 'No additional notes'}",
                notification_type=NotificationType.LOGISTICS,
                action_url=f"/orders/{transport.order.id}"
            )
        except Exception:
            pass

        return Response({
            "id": transport.id,
            "order_number": transport.order.order_number,
            "status": transport.status,
            "tracking_notes": transport.tracking_notes,
            "delivered_at": transport.delivered_at,
            "message": f"Logistics status updated to '{transport.get_status_display()}'."
        })

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsLogisticsParticipant])
    def track(self, request, pk=None):
        """Detailed tracking endpoint for Buyer, Farmer, and Transporter."""
        transport = self.get_object()
        serializer = TransportRequestDetailSerializer(transport)
        return Response(serializer.data)
