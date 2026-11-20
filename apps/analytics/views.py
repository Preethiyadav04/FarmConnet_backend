from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Sum, Count, Avg, Q
from django.contrib.auth import get_user_model
from decimal import Decimal

from apps.crops.models import Crop, CropStatus
from apps.orders.models import Order, OrderItem, Payment, OrderStatus, PaymentStatus
from apps.logistics.models import TransportRequest, TransportStatus
from apps.reviews.models import Review, Favorite
from apps.accounts.models import UserRole

User = get_user_model()


def get_farmer_analytics_data(farmer_user):
    """Calculates comprehensive real analytics for a farmer from live MySQL records."""
    total_crops = Crop.objects.filter(farmer=farmer_user).count()
    active_crops = Crop.objects.filter(farmer=farmer_user, status=CropStatus.ACTIVE).count()
    sold_out_crops = Crop.objects.filter(farmer=farmer_user, status=CropStatus.SOLD_OUT).count()

    orders_qs = Order.objects.filter(farmer=farmer_user)
    total_orders = orders_qs.count()
    pending_orders = orders_qs.filter(status=OrderStatus.PENDING).count()
    confirmed_orders = orders_qs.filter(status=OrderStatus.CONFIRMED).count()
    processing_orders = orders_qs.filter(status=OrderStatus.PROCESSING).count()
    dispatched_orders = orders_qs.filter(status=OrderStatus.DISPATCHED).count()
    completed_orders = orders_qs.filter(status=OrderStatus.DELIVERED).count()
    cancelled_orders = orders_qs.filter(status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED]).count()

    # Actual completed sales revenue based on delivered orders or completed payments
    completed_sales = orders_qs.filter(status=OrderStatus.DELIVERED).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')

    received_payments = Payment.objects.filter(
        order__farmer=farmer_user,
        payment_status=PaymentStatus.COMPLETED
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Most ordered crops aggregation
    top_crops = OrderItem.objects.filter(order__farmer=farmer_user)\
        .values('crop_title', 'crop_listing_id', 'unit')\
        .annotate(
            total_quantity=Sum('quantity'),
            order_count=Count('order_id', distinct=True),
            total_sales=Sum('subtotal')
        ).order_by('-total_quantity')[:5]

    most_ordered_list = [
        {
            "crop_id": item['crop_listing_id'],
            "crop_title": item['crop_title'],
            "total_quantity_sold": str(item['total_quantity']),
            "unit": item['unit'],
            "times_ordered": item['order_count'],
            "gross_revenue": str(item['total_sales'])
        }
        for item in top_crops
    ]

    # Customer ratings & reviews summary
    review_stats = Review.objects.filter(farmer=farmer_user).aggregate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )
    avg_score = round(review_stats['avg_rating'], 2) if review_stats['avg_rating'] else 0.0

    return {
        "role": "farmer",
        "farmer_id": farmer_user.id,
        "farmer_name": farmer_user.username,
        "crop_listings": {
            "total": total_crops,
            "active": active_crops,
            "sold_out": sold_out_crops
        },
        "orders_summary": {
            "total_received": total_orders,
            "pending": pending_orders,
            "confirmed": confirmed_orders,
            "processing": processing_orders,
            "dispatched": dispatched_orders,
            "completed": completed_orders,
            "cancelled_or_rejected": cancelled_orders
        },
        "revenue": {
            "completed_orders_total": str(completed_sales),
            "verified_payments_received": str(received_payments)
        },
        "most_ordered_crops": most_ordered_list,
        "reputation": {
            "average_rating": avg_score,
            "total_reviews": review_stats['count'] or 0
        }
    }


def get_buyer_analytics_data(buyer_user):
    """Calculates comprehensive real analytics for a buyer from live MySQL records."""
    orders_qs = Order.objects.filter(buyer=buyer_user)
    total_orders = orders_qs.count()
    pending_orders = orders_qs.filter(
        status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.DISPATCHED]
    ).count()
    completed_orders = orders_qs.filter(status=OrderStatus.DELIVERED).count()
    cancelled_orders = orders_qs.filter(status=OrderStatus.CANCELLED).count()

    total_purchase_amount = orders_qs.filter(status=OrderStatus.DELIVERED).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')

    active_order_value = orders_qs.filter(
        status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.DISPATCHED]
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    # Favorite crops bookmarked by this buyer
    favorites = Favorite.objects.filter(buyer=buyer_user).select_related('crop_listing', 'crop_listing__farmer')
    favorite_list = [
        {
            "crop_id": f.crop_listing.id,
            "crop_name": f.crop_listing.crop_name,
            "price_per_unit": str(f.crop_listing.price_per_unit),
            "unit": f.crop_listing.unit,
            "farmer": f.crop_listing.farmer.username
        }
        for f in favorites[:5]
    ]

    # Most purchased crops
    top_purchases = OrderItem.objects.filter(order__buyer=buyer_user)\
        .values('crop_title', 'crop_listing_id', 'unit')\
        .annotate(
            total_quantity=Sum('quantity'),
            order_count=Count('order_id', distinct=True),
            total_spent=Sum('subtotal')
        ).order_by('-total_quantity')[:5]

    most_purchased_list = [
        {
            "crop_id": item['crop_listing_id'],
            "crop_title": item['crop_title'],
            "total_quantity": str(item['total_quantity']),
            "unit": item['unit'],
            "orders_count": item['order_count'],
            "total_spent": str(item['total_spent'])
        }
        for item in top_purchases
    ]

    return {
        "role": "buyer",
        "buyer_id": buyer_user.id,
        "buyer_name": buyer_user.username,
        "orders_summary": {
            "total_placed": total_orders,
            "pending_or_in_progress": pending_orders,
            "completed": completed_orders,
            "cancelled": cancelled_orders
        },
        "expenditure": {
            "total_spent": str(total_purchase_amount + active_order_value),
            "completed_purchases_total": str(total_purchase_amount),
            "active_orders_value": str(active_order_value)
        },
        "favorite_crops": favorite_list,
        "most_purchased_crops": most_purchased_list
    }


def get_transporter_analytics_data(transporter_user):
    """Calculates comprehensive real analytics for a transporter from live MySQL records."""
    assigned_qs = TransportRequest.objects.filter(transporter=transporter_user)
    total_assigned = assigned_qs.count()
    pending_deliveries = assigned_qs.filter(
        status__in=[TransportStatus.ACCEPTED, TransportStatus.PICKED_UP, TransportStatus.IN_TRANSIT]
    ).count()
    completed_deliveries = assigned_qs.filter(status=TransportStatus.DELIVERED).count()
    cancelled_deliveries = assigned_qs.filter(status=TransportStatus.CANCELLED).count()

    status_summary = {s[0]: 0 for s in TransportStatus.choices}
    for item in assigned_qs.values('status').annotate(c=Count('id')):
        status_summary[item['status']] = item['c']

    total_freight = assigned_qs.filter(status=TransportStatus.DELIVERED).aggregate(
        total=Sum('final_charge')
    )['total'] or Decimal('0.00')

    open_market_jobs = TransportRequest.objects.filter(
        status=TransportStatus.REQUESTED,
        transporter__isnull=True
    ).count()

    return {
        "role": "transporter",
        "transporter_id": transporter_user.id,
        "transporter_name": transporter_user.username,
        "deliveries_summary": {
            "total_assigned": total_assigned,
            "in_progress": pending_deliveries,
            "completed": completed_deliveries,
            "cancelled": cancelled_deliveries
        },
        "delivery_status_breakdown": status_summary,
        "earnings": {
            "completed_freight_total": str(total_freight)
        },
        "available_market_jobs": open_market_jobs
    }


def get_admin_analytics_data():
    """Calculates platform-wide analytics for administration and governance."""
    total_users = User.objects.count()
    users_by_role = {r[0]: 0 for r in UserRole.choices}
    for item in User.objects.values('role').annotate(c=Count('id')):
        users_by_role[item['role']] = item['c']

    total_crops = Crop.objects.count()
    active_crops = Crop.objects.filter(status=CropStatus.ACTIVE).count()
    sold_out_crops = Crop.objects.filter(status=CropStatus.SOLD_OUT).count()

    total_orders = Order.objects.count()
    orders_by_status = {s[0]: 0 for s in OrderStatus.choices}
    for item in Order.objects.values('status').annotate(c=Count('id')):
        orders_by_status[item['status']] = item['c']

    platform_gmv = Order.objects.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    settled_sales = Payment.objects.filter(payment_status=PaymentStatus.COMPLETED).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    total_deliveries = TransportRequest.objects.count()
    completed_deliveries = TransportRequest.objects.filter(status=TransportStatus.DELIVERED).count()

    # Recent platform activities
    recent_orders = [
        {
            "id": o.id,
            "order_number": o.order_number,
            "buyer": o.buyer.username,
            "farmer": o.farmer.username,
            "total_amount": str(o.total_amount),
            "status": o.status,
            "created_at": o.created_at.strftime('%Y-%m-%d %H:%M')
        }
        for o in Order.objects.select_related('buyer', 'farmer').order_by('-created_at')[:5]
    ]

    recent_users = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "date_joined": u.date_joined.strftime('%Y-%m-%d %H:%M')
        }
        for u in User.objects.order_by('-date_joined')[:5]
    ]

    recent_reviews = [
        {
            "id": r.id,
            "rating": r.rating,
            "buyer": r.buyer.username,
            "farmer": r.farmer.username,
            "comment": r.comment[:80] + '...' if len(r.comment) > 80 else r.comment,
            "created_at": r.created_at.strftime('%Y-%m-%d %H:%M')
        }
        for r in Review.objects.select_related('buyer', 'farmer').order_by('-created_at')[:5]
    ]

    return {
        "role": "admin",
        "platform_overview": {
            "total_users": total_users,
            "users_by_role": users_by_role,
            "total_crops": total_crops,
            "active_crops": active_crops,
            "sold_out_crops": sold_out_crops,
            "total_orders": total_orders,
            "orders_by_status": orders_by_status,
            "total_deliveries": total_deliveries,
            "completed_deliveries": completed_deliveries
        },
        "financial_summary": {
            "gross_merchandise_value": str(platform_gmv),
            "settled_payments_total": str(settled_sales)
        },
        "recent_activity": {
            "orders": recent_orders,
            "users": recent_users,
            "reviews": recent_reviews
        }
    }


class DashboardAnalyticsView(APIView):
    """
    Universal Dashboard Analytics Entrypoint.
    Inspects user role and serves the corresponding role-based analytics payload automatically.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            return Response(get_admin_analytics_data())
        elif getattr(user, 'is_farmer', False):
            return Response(get_farmer_analytics_data(user))
        elif getattr(user, 'is_buyer', False):
            return Response(get_buyer_analytics_data(user))
        elif getattr(user, 'is_transporter', False):
            return Response(get_transporter_analytics_data(user))
        return Response({"detail": "User role does not have an active dashboard."}, status=status.HTTP_400_BAD_REQUEST)


class FarmerAnalyticsView(APIView):
    """Farmer role analytics API."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # Allow Admin to inspect any farmer or own
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            farmer_id = request.query_params.get('farmer_id')
            if farmer_id:
                try:
                    target_farmer = User.objects.get(id=farmer_id, role=UserRole.FARMER)
                except User.DoesNotExist:
                    return Response({"detail": "Farmer with specified ID not found."}, status=status.HTTP_404_NOT_FOUND)
                return Response(get_farmer_analytics_data(target_farmer))

        if not getattr(user, 'is_farmer', False):
            return Response({"detail": "Access denied: Farmer role required."}, status=status.HTTP_403_FORBIDDEN)

        return Response(get_farmer_analytics_data(user))


class BuyerAnalyticsView(APIView):
    """Buyer role analytics API."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'is_admin_user', False) or user.is_superuser:
            buyer_id = request.query_params.get('buyer_id')
            if buyer_id:
                try:
                    target_buyer = User.objects.get(id=buyer_id, role=UserRole.BUYER)
                except User.DoesNotExist:
                    return Response({"detail": "Buyer with specified ID not found."}, status=status.HTTP_404_NOT_FOUND)
                return Response(get_buyer_analytics_data(target_buyer))

        if not getattr(user, 'is_buyer', False):
            return Response({"detail": "Access denied: Buyer role required."}, status=status.HTTP_403_FORBIDDEN)

        return Response(get_buyer_analytics_data(user))


class TransporterAnalyticsView(APIView):
    """Transporter role analytics API."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (getattr(user, 'is_transporter', False) or getattr(user, 'is_admin_user', False) or user.is_superuser):
            return Response({"detail": "Access denied: Transporter role required."}, status=status.HTTP_403_FORBIDDEN)

        return Response(get_transporter_analytics_data(user))


class AdminAnalyticsView(APIView):
    """Platform administrator governance and financial reporting API."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (getattr(user, 'is_admin_user', False) or user.is_staff or user.is_superuser):
            return Response({"detail": "Access denied: Platform administrator credentials required."}, status=status.HTTP_403_FORBIDDEN)

        return Response(get_admin_analytics_data())
