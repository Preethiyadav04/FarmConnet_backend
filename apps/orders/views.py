from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from .models import (
    Order, OrderItem, Payment, PriceNegotiation,
    OrderStatus, PaymentStatus, PaymentMethod, NegotiationStatus
)
from .serializers import (
    OrderListSerializer, OrderDetailSerializer, OrderCreateSerializer,
    PriceNegotiationSerializer, PaymentSerializer
)
from .permissions import IsOrderParticipant, IsNegotiationParticipant
from apps.crops.models import Crop, CropStatus


class StandardResultsPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 50


class OrderViewSet(viewsets.ModelViewSet):
    """
    Agricultural Purchase Order Management.
    - Concurrency-safe checkout with row-level locking (select_for_update).
    - Role-isolated viewsets: Buyers see own orders, Farmers see orders for their harvest.
    """
    pagination_class = StandardResultsPagination
    permission_classes = [permissions.IsAuthenticated, IsOrderParticipant]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['order_number', 'items__crop_title', 'delivery_city']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderListSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()

        qs = Order.objects.select_related('buyer', 'farmer', 'payment').prefetch_related('items')

        # Admin can view all platform transactions
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            role_filter = self.request.query_params.get('view_as')
            if role_filter == 'buyer':
                return qs.filter(buyer=user)
            elif role_filter == 'farmer':
                return qs.filter(farmer=user)
            return qs

        # Farmers see orders where they are the supplier
        if getattr(user, 'is_farmer', False):
            # Check if farmer also has buyer purchases
            view_as = self.request.query_params.get('view_as')
            if view_as == 'buyer':
                return qs.filter(buyer=user)
            return qs.filter(farmer=user)

        # Buyers see only orders they placed
        return qs.filter(buyer=user)

    def create(self, request, *args, **kwargs):
        if getattr(request.user, 'is_transporter', False) and not (getattr(request.user, 'is_admin_user', False) or request.user.is_superuser):
            return Response(
                {"detail": "Transporters cannot place crop purchase orders."},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOrderParticipant])
    def accept_order(self, request, pk=None):
        """Farmer accepts incoming pending order."""
        order = self.get_object()
        if order.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the supplier farmer can accept this order."}, status=status.HTTP_403_FORBIDDEN)

        if order.status != OrderStatus.PENDING:
            return Response({"detail": f"Order is already '{order.status}' and cannot be accepted."}, status=status.HTTP_400_BAD_REQUEST)

        order.status = OrderStatus.CONFIRMED
        order.save(update_fields=['status', 'updated_at'])

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=order.buyer,
                title="Order Confirmed!",
                message=f"Farmer {order.farmer.username} confirmed your order #{order.order_number}.",
                notification_type=NotificationType.ORDER,
                action_url=f"/orders/{order.id}"
            )
        except Exception:
            pass

        return Response({"order_number": order.order_number, "status": order.status, "message": "Order successfully confirmed."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOrderParticipant])
    def reject_order(self, request, pk=None):
        """Farmer rejects order and restores crop stock atomically."""
        order = self.get_object()
        if order.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the supplier farmer can reject this order."}, status=status.HTTP_403_FORBIDDEN)

        if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
            return Response({"detail": f"Order in status '{order.status}' cannot be rejected."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Restore inventory for all items
            for item in order.items.select_for_update():
                crop = Crop.objects.select_for_update().get(id=item.crop_listing_id)
                crop.quantity_available += item.quantity
                if crop.status == CropStatus.SOLD_OUT and crop.quantity_available > 0:
                    crop.status = CropStatus.ACTIVE
                crop.save(update_fields=['quantity_available', 'status', 'updated_at'])

            order.status = OrderStatus.REJECTED
            reason = request.data.get('reason', '')
            if reason:
                order.notes = f"{order.notes}\n[Farmer Rejection Reason]: {reason}".strip()
            order.save(update_fields=['status', 'notes', 'updated_at'])

            # Automatically cancel associated transport request so it does not remain active
            try:
                from apps.logistics.models import TransportRequest, TransportStatus
                tr = getattr(order, 'transport_request', None)
                if tr and tr.status != TransportStatus.CANCELLED:
                    tr.status = TransportStatus.CANCELLED
                    tr.tracking_notes = f"{tr.tracking_notes}\nOrder rejected by farmer - transport cancelled.".strip()
                    tr.save(update_fields=['status', 'tracking_notes', 'updated_at'])
            except Exception:
                pass

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=order.buyer,
                title="Order Rejected",
                message=f"Farmer {order.farmer.username} was unable to accept order #{order.order_number}.",
                notification_type=NotificationType.ORDER,
                action_url=f"/orders/{order.id}"
            )
        except Exception:
            pass

        return Response({"order_number": order.order_number, "status": order.status, "message": "Order rejected. Stock returned to inventory."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOrderParticipant])
    def cancel_order(self, request, pk=None):
        """Buyer cancels pending order before dispatch and restores crop stock atomically."""
        order = self.get_object()
        if order.buyer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the buyer who placed this order can cancel it."}, status=status.HTTP_403_FORBIDDEN)

        if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
            return Response(
                {"detail": f"Orders in '{order.status}' stage cannot be cancelled once processing or dispatched."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            for item in order.items.select_for_update():
                crop = Crop.objects.select_for_update().get(id=item.crop_listing_id)
                crop.quantity_available += item.quantity
                if crop.status == CropStatus.SOLD_OUT and crop.quantity_available > 0:
                    crop.status = CropStatus.ACTIVE
                crop.save(update_fields=['quantity_available', 'status', 'updated_at'])

            order.status = OrderStatus.CANCELLED
            order.save(update_fields=['status', 'updated_at'])

            # Automatically cancel associated transport request so it does not remain active
            try:
                from apps.logistics.models import TransportRequest, TransportStatus
                tr = getattr(order, 'transport_request', None)
                if tr and tr.status != TransportStatus.CANCELLED:
                    tr.status = TransportStatus.CANCELLED
                    tr.tracking_notes = f"{tr.tracking_notes}\nOrder cancelled by buyer - transport cancelled.".strip()
                    tr.save(update_fields=['status', 'tracking_notes', 'updated_at'])
            except Exception:
                pass

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=order.farmer,
                title="Order Cancelled",
                message=f"Buyer {order.buyer.username} cancelled order #{order.order_number}.",
                notification_type=NotificationType.ORDER,
                action_url=f"/orders/{order.id}"
            )
        except Exception:
            pass

        return Response({"order_number": order.order_number, "status": order.status, "message": "Order cancelled. Inventory restored."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOrderParticipant])
    def update_payment_status(self, request, pk=None):
        """Supplier farmer or Admin marks payment as received/completed."""
        order = self.get_object()
        if order.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the farmer or admin can verify payment collection."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('payment_status')
        if new_status not in [PaymentStatus.PENDING, PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]:
            return Response({"detail": f"Invalid payment status choice: '{new_status}'"}, status=status.HTTP_400_BAD_REQUEST)

        payment, _ = Payment.objects.get_or_create(order=order, defaults={'amount': order.total_amount})
        payment.payment_status = new_status
        if new_status == PaymentStatus.COMPLETED and not payment.paid_at:
            payment.paid_at = timezone.now()
        ref = request.data.get('transaction_reference')
        if ref:
            payment.transaction_reference = ref
        payment.save()

        if new_status == PaymentStatus.COMPLETED:
            try:
                from apps.notifications.models import send_notification, NotificationType
                send_notification(
                    recipient=order.buyer,
                    title="Payment Received",
                    message=f"Payment for order #{order.order_number} has been verified and marked completed.",
                    notification_type=NotificationType.PAYMENT,
                    action_url=f"/orders/{order.id}"
                )
            except Exception:
                pass

        return Response({
            "order_number": order.order_number,
            "payment_status": payment.payment_status,
            "paid_at": payment.paid_at,
            "message": "Payment status updated."
        })


class PriceNegotiationViewSet(viewsets.ModelViewSet):
    """
    Farmer-Buyer Price Negotiation & Counter-Offer Engine.
    - Buyers submit offers with custom proposed price/quantity.
    - Farmers can Accept, Reject, or propose Counter-offers.
    - Accepted negotiations can be converted to confirmed orders directly.
    """
    pagination_class = StandardResultsPagination
    permission_classes = [permissions.IsAuthenticated, IsNegotiationParticipant]
    ordering = ['-created_at']

    def get_serializer_class(self):
        return PriceNegotiationSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PriceNegotiation.objects.none()

        qs = PriceNegotiation.objects.select_related('buyer', 'listing', 'listing__farmer', 'converted_order')

        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            return qs

        # Farmers see incoming offers on their crops
        if getattr(user, 'is_farmer', False):
            return qs.filter(Q(listing__farmer=user) | Q(buyer=user))

        # Buyers see only offers they submitted
        return qs.filter(buyer=user)

    def create(self, request, *args, **kwargs):
        if getattr(request.user, 'is_transporter', False) and not (getattr(request.user, 'is_admin_user', False) or request.user.is_superuser):
            return Response(
                {"detail": "Transporters cannot submit price negotiations."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        offer = serializer.save()
        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=offer.listing.farmer,
                title="New Price Offer Received",
                message=f"Buyer {offer.buyer.username} proposed ₹{offer.offered_price_per_unit}/{offer.listing.unit} for '{offer.crop_name}'.",
                notification_type=NotificationType.NEGOTIATION,
                action_url=f"/negotiations/{offer.id}"
            )
        except Exception:
            pass

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNegotiationParticipant])
    def accept(self, request, pk=None):
        """Farmer accepts the buyer's offer."""
        offer = self.get_object()
        if offer.listing.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the crop owner farmer can accept this offer."}, status=status.HTTP_403_FORBIDDEN)

        if offer.status != NegotiationStatus.PENDING:
            return Response({"detail": f"Offer in status '{offer.status}' cannot be accepted."}, status=status.HTTP_400_BAD_REQUEST)

        offer.status = NegotiationStatus.ACCEPTED
        notes = request.data.get('farmer_notes', '')
        if notes:
            offer.farmer_notes = notes
        offer.save()

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=offer.buyer,
                title="Price Offer Accepted!",
                message=f"Farmer {offer.listing.farmer.username} accepted your offer on '{offer.crop_name}'. You can now place the order.",
                notification_type=NotificationType.NEGOTIATION,
                action_url=f"/negotiations/{offer.id}"
            )
        except Exception:
            pass

        return Response({"id": offer.id, "status": offer.status, "message": "Offer accepted. Buyer may now convert to order."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNegotiationParticipant])
    def reject(self, request, pk=None):
        """Farmer rejects the buyer's offer."""
        offer = self.get_object()
        if offer.listing.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the crop owner farmer can reject this offer."}, status=status.HTTP_403_FORBIDDEN)

        if offer.status not in [NegotiationStatus.PENDING, NegotiationStatus.COUNTERED]:
            return Response({"detail": f"Offer in status '{offer.status}' cannot be rejected."}, status=status.HTTP_400_BAD_REQUEST)

        offer.status = NegotiationStatus.REJECTED
        notes = request.data.get('farmer_notes', '')
        if notes:
            offer.farmer_notes = notes
        offer.save()

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=offer.buyer,
                title="Price Offer Declined",
                message=f"Farmer {offer.listing.farmer.username} declined your offer on '{offer.crop_name}'.",
                notification_type=NotificationType.NEGOTIATION,
                action_url=f"/negotiations/{offer.id}"
            )
        except Exception:
            pass

        return Response({"id": offer.id, "status": offer.status, "message": "Offer rejected."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNegotiationParticipant])
    def counter(self, request, pk=None):
        """Farmer proposes a counter-offer price."""
        offer = self.get_object()
        if offer.listing.farmer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the crop owner farmer can make a counter-offer."}, status=status.HTTP_403_FORBIDDEN)

        if offer.status not in [NegotiationStatus.PENDING, NegotiationStatus.COUNTERED]:
            return Response({"detail": f"Cannot counter an offer in status '{offer.status}'."}, status=status.HTTP_400_BAD_REQUEST)

        counter_price = request.data.get('counter_price_per_unit')
        if not counter_price:
            return Response({"detail": "Please provide 'counter_price_per_unit'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            counter_price = float(counter_price)
            if counter_price <= 0:
                raise ValueError()
        except ValueError:
            return Response({"detail": "Counter price must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)

        offer.counter_price_per_unit = counter_price
        offer.status = NegotiationStatus.COUNTERED
        notes = request.data.get('farmer_notes', '')
        if notes:
            offer.farmer_notes = notes
        offer.save()

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=offer.buyer,
                title="Counter-Offer Received",
                message=f"Farmer {offer.listing.farmer.username} proposed counter-price ₹{offer.counter_price_per_unit}/{offer.listing.unit} on '{offer.crop_name}'.",
                notification_type=NotificationType.NEGOTIATION,
                action_url=f"/negotiations/{offer.id}"
            )
        except Exception:
            pass

        return Response({
            "id": offer.id,
            "status": offer.status,
            "counter_price_per_unit": str(offer.counter_price_per_unit),
            "message": "Counter-offer submitted to buyer."
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNegotiationParticipant])
    def accept_counter(self, request, pk=None):
        """Buyer accepts the farmer's counter-offer."""
        offer = self.get_object()
        if offer.buyer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the buyer can accept the counter-offer."}, status=status.HTTP_403_FORBIDDEN)

        if offer.status != NegotiationStatus.COUNTERED:
            return Response({"detail": "No pending counter-offer to accept."}, status=status.HTTP_400_BAD_REQUEST)

        offer.status = NegotiationStatus.ACCEPTED
        offer.save()

        try:
            from apps.notifications.models import send_notification, NotificationType
            send_notification(
                recipient=offer.listing.farmer,
                title="Counter-Offer Accepted!",
                message=f"Buyer {offer.buyer.username} accepted your counter-offer of ₹{offer.counter_price_per_unit}/{offer.listing.unit} on '{offer.crop_name}'.",
                notification_type=NotificationType.NEGOTIATION,
                action_url=f"/negotiations/{offer.id}"
            )
        except Exception:
            pass

        return Response({"id": offer.id, "status": offer.status, "message": "Counter-offer accepted. Ready to convert to order."})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNegotiationParticipant])
    def convert_to_order(self, request, pk=None):
        """
        Buyer converts an accepted negotiation into a confirmed purchase order.
        Uses final agreed price and locks stock atomically.
        """
        offer = self.get_object()
        if offer.buyer != request.user and not getattr(request.user, 'is_admin_user', False):
            return Response({"detail": "Only the buyer can finalize this negotiation into an order."}, status=status.HTTP_403_FORBIDDEN)

        if offer.status != NegotiationStatus.ACCEPTED:
            return Response({"detail": "Only 'accepted' negotiations can be converted to an order."}, status=status.HTTP_400_BAD_REQUEST)

        delivery_address = request.data.get('delivery_address', 'Buyer Registered Delivery Address')
        delivery_city = request.data.get('delivery_city', offer.listing.location_city)
        delivery_state = request.data.get('delivery_state', offer.listing.location_state)
        contact_phone = request.data.get('contact_phone', request.user.phone or '9876543210')

        with transaction.atomic():
            crop = Crop.objects.select_for_update().get(id=offer.listing_id)
            if crop.quantity_available < offer.quantity:
                return Response(
                    {"detail": f"Insufficient stock remaining ({crop.quantity_available} {crop.unit} available)."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            agreed_unit_price = offer.final_agreed_price
            order_total = offer.quantity * agreed_unit_price

            crop.quantity_available -= offer.quantity
            if crop.quantity_available == 0:
                crop.status = CropStatus.SOLD_OUT
            crop.save(update_fields=['quantity_available', 'status', 'updated_at'])

            order = Order.objects.create(
                order_number=Order.generate_order_number(),
                buyer=offer.buyer,
                farmer=crop.farmer,
                total_amount=order_total,
                status=OrderStatus.CONFIRMED,  # Already pre-agreed between both parties
                delivery_address=delivery_address,
                delivery_city=delivery_city,
                delivery_state=delivery_state,
                contact_phone=contact_phone,
                notes=f"Created via Price Negotiation #{offer.id}"
            )

            OrderItem.objects.create(
                order=order,
                crop_listing=crop,
                crop_title=crop.crop_name,
                quantity=offer.quantity,
                unit=crop.unit,
                unit_price=agreed_unit_price,
                subtotal=order_total
            )

            Payment.objects.create(
                order=order,
                payment_method=PaymentMethod.COD,
                payment_status=PaymentStatus.PENDING,
                amount=order_total
            )

            offer.status = NegotiationStatus.CONVERTED
            offer.converted_order = order
            offer.save(update_fields=['status', 'converted_order', 'updated_at'])

            if request.data.get('request_transport', False):
                try:
                    from apps.logistics.models import TransportRequest, TransportStatus
                    TransportRequest.objects.create(
                        order=order,
                        requester=offer.buyer,
                        pickup_address=f"{crop.location_city}, {crop.location_state}",
                        pickup_city=crop.location_city,
                        drop_address=delivery_address,
                        drop_city=delivery_city,
                        estimated_distance_km=50,
                        estimated_cost=round(float(order_total) * 0.08, 2) or 500.00,
                        status=TransportStatus.REQUESTED
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Could not auto-create transport request: {e}")

        return Response({
            "negotiation_id": offer.id,
            "order_id": order.id,
            "order_number": order.order_number,
            "total_amount": str(order.total_amount),
            "agreed_unit_price": str(agreed_unit_price),
            "status": order.status,
            "message": "Negotiation successfully converted to confirmed purchase order!"
        }, status=status.HTTP_201_CREATED)
