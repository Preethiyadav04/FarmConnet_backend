from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem, Payment, PriceNegotiation, OrderStatus, PaymentMethod, PaymentStatus, NegotiationStatus
from apps.crops.models import Crop, CropStatus


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'payment_method', 'payment_status', 'amount',
            'transaction_reference', 'paid_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'amount', 'created_at', 'updated_at']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            'id', 'crop_listing', 'crop_title', 'quantity',
            'unit', 'unit_price', 'subtotal'
        ]
        read_only_fields = ['id', 'subtotal']


class OrderListSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()
    farmer_name = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    payment_status = serializers.CharField(source='payment.payment_status', default='pending', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer', 'buyer_name', 'farmer', 'farmer_name',
            'total_amount', 'status', 'delivery_city', 'delivery_state',
            'items', 'items_count', 'payment_status', 'created_at'
        ]

    def get_buyer_name(self, obj):
        profile = getattr(obj.buyer, 'user_profile', None)
        return profile.full_name if profile and profile.full_name else obj.buyer.username

    def get_farmer_name(self, obj):
        farmer_prof = getattr(obj.farmer, 'farmer_profile', None)
        if farmer_prof and farmer_prof.farm_name:
            return farmer_prof.farm_name
        profile = getattr(obj.farmer, 'user_profile', None)
        return profile.full_name if profile and profile.full_name else obj.farmer.username

    def get_items_count(self, obj):
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    buyer_name = serializers.SerializerMethodField()
    farmer_name = serializers.SerializerMethodField()
    transport_status = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer', 'buyer_name', 'farmer', 'farmer_name',
            'total_amount', 'status', 'delivery_address', 'delivery_city',
            'delivery_state', 'delivery_pincode', 'contact_phone', 'notes',
            'items', 'payment', 'transport_status', 'created_at', 'updated_at'
        ]

    def get_buyer_name(self, obj):
        profile = getattr(obj.buyer, 'user_profile', None)
        return profile.full_name if profile and profile.full_name else obj.buyer.username

    def get_farmer_name(self, obj):
        farmer_prof = getattr(obj.farmer, 'farmer_profile', None)
        if farmer_prof and farmer_prof.farm_name:
            return farmer_prof.farm_name
        profile = getattr(obj.farmer, 'user_profile', None)
        return profile.full_name if profile and profile.full_name else obj.farmer.username

    def get_transport_status(self, obj):
        transport = getattr(obj, 'transport_request', None)
        if transport:
            return {
                'id': transport.id,
                'status': transport.status,
                'transporter': transport.transporter.username if transport.transporter else None,
                'tracking_notes': transport.tracking_notes
            }
        return None


class OrderCreateSerializer(serializers.Serializer):
    """
    Direct checkout serializer with concurrency control and row-level locking
    (select_for_update) to strictly prevent overselling.
    """
    crop_id = serializers.IntegerField(required=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    delivery_address = serializers.CharField(required=True)
    delivery_city = serializers.CharField(required=True)
    delivery_state = serializers.CharField(required=True)
    delivery_pincode = serializers.CharField(required=False, default='')
    contact_phone = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, default='')
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.COD)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity ordered must be greater than zero.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        buyer = request.user
        crop_id = validated_data['crop_id']
        requested_qty = validated_data['quantity']

        # Atomic transaction with pessimistic row-locking to prevent race conditions & overselling
        with transaction.atomic():
            try:
                crop = Crop.objects.select_for_update().get(id=crop_id)
            except Crop.DoesNotExist:
                raise serializers.ValidationError({"crop_id": "Specified crop listing does not exist."})

            if crop.farmer == buyer:
                raise serializers.ValidationError({"crop_id": "Farmers cannot purchase their own crops."})

            if crop.status != CropStatus.ACTIVE:
                raise serializers.ValidationError({"crop_id": f"This crop is currently '{crop.status}' and not open for orders."})

            if requested_qty < crop.minimum_order_quantity:
                raise serializers.ValidationError({
                    "quantity": f"Minimum order quantity for this crop is {crop.minimum_order_quantity} {crop.unit}."
                })

            if crop.quantity_available < requested_qty:
                raise serializers.ValidationError({
                    "quantity": f"Insufficient stock. Only {crop.quantity_available} {crop.unit} available."
                })

            # Calculate total
            total_amount = requested_qty * crop.price_per_unit

            # Deduct inventory atomically
            crop.quantity_available -= requested_qty
            if crop.quantity_available == 0:
                crop.status = CropStatus.SOLD_OUT
            crop.save(update_fields=['quantity_available', 'status', 'updated_at'])

            # Create Order
            order = Order.objects.create(
                order_number=Order.generate_order_number(),
                buyer=buyer,
                farmer=crop.farmer,
                total_amount=total_amount,
                status=OrderStatus.PENDING,
                delivery_address=validated_data['delivery_address'],
                delivery_city=validated_data['delivery_city'],
                delivery_state=validated_data['delivery_state'],
                delivery_pincode=validated_data.get('delivery_pincode', ''),
                contact_phone=validated_data['contact_phone'],
                notes=validated_data.get('notes', '')
            )

            # Create OrderItem
            OrderItem.objects.create(
                order=order,
                crop_listing=crop,
                crop_title=crop.crop_name,
                quantity=requested_qty,
                unit=crop.unit,
                unit_price=crop.price_per_unit,
                subtotal=total_amount
            )

            # Create Payment Record
            Payment.objects.create(
                order=order,
                payment_method=validated_data.get('payment_method', PaymentMethod.COD),
                payment_status=PaymentStatus.PENDING,
                amount=total_amount
            )

            # Create initial TransportRequest so transporters can accept it
            try:
                from apps.logistics.models import TransportRequest, TransportStatus
                TransportRequest.objects.create(
                    order=order,
                    requester=buyer,
                    pickup_address=f"{crop.location_city}, {crop.location_state}",
                    pickup_city=crop.location_city,
                    drop_address=validated_data['delivery_address'],
                    drop_city=validated_data['delivery_city'],
                    estimated_cost=round(float(total_amount) * 0.08, 2) or 500.00,
                    status=TransportStatus.REQUESTED
                )
            except Exception:
                pass  # Logistics record is optional helper

            # Notify Farmer of incoming order
            try:
                from apps.notifications.models import send_notification, NotificationType
                send_notification(
                    recipient=crop.farmer,
                    title="New Order Received!",
                    message=f"Buyer {buyer.username} placed order #{order.order_number} for ₹{total_amount}.",
                    notification_type=NotificationType.ORDER,
                    action_url=f"/orders/{order.id}"
                )
            except Exception:
                pass

        return order


class PriceNegotiationSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source='listing.crop_name', read_only=True)
    crop_unit = serializers.CharField(source='listing.unit', read_only=True)
    farmer_listed_price = serializers.DecimalField(source='listing.price_per_unit', max_digits=10, decimal_places=2, read_only=True)
    buyer_name = serializers.SerializerMethodField()
    farmer_name = serializers.SerializerMethodField()
    final_agreed_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = PriceNegotiation
        fields = [
            'id', 'listing', 'crop_name', 'crop_unit', 'buyer', 'buyer_name',
            'farmer_name', 'farmer_listed_price', 'offered_price_per_unit',
            'quantity', 'total_offered_amount', 'counter_price_per_unit',
            'final_agreed_price', 'status', 'message', 'farmer_notes',
            'converted_order', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'buyer', 'total_offered_amount', 'status',
            'farmer_notes', 'converted_order', 'created_at', 'updated_at'
        ]

    def get_buyer_name(self, obj):
        profile = getattr(obj.buyer, 'user_profile', None)
        return profile.full_name if profile and profile.full_name else obj.buyer.username

    def get_farmer_name(self, obj):
        farmer_prof = getattr(obj.listing.farmer, 'farmer_profile', None)
        if farmer_prof and farmer_prof.farm_name:
            return farmer_prof.farm_name
        return obj.listing.farmer.username

    def validate_offered_price_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Offered price per unit must be greater than zero.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        listing = attrs.get('listing')
        qty = attrs.get('quantity')
        request = self.context.get('request')

        if listing and request:
            if listing.farmer == request.user:
                raise serializers.ValidationError({"listing": "Farmers cannot make purchase offers on their own crop listings."})
            if listing.status != CropStatus.ACTIVE:
                raise serializers.ValidationError({"listing": "Offers can only be submitted on available active crops."})
            if qty and qty > listing.quantity_available:
                raise serializers.ValidationError({
                    "quantity": f"Requested quantity ({qty}) exceeds available stock ({listing.quantity_available} {listing.unit})."
                })
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['buyer'] = request.user
        qty = validated_data['quantity']
        offered_price = validated_data['offered_price_per_unit']
        validated_data['total_offered_amount'] = qty * offered_price
        validated_data['status'] = NegotiationStatus.PENDING
        return super().create(validated_data)
