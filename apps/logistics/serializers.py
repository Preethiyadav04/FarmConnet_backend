from rest_framework import serializers
from django.utils import timezone
from .models import TransportRequest, TransportStatus


class TransportRequestListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    transporter_name = serializers.SerializerMethodField()

    class Meta:
        model = TransportRequest
        fields = [
            'id', 'order', 'order_number', 'pickup_city', 'drop_city',
            'estimated_distance_km', 'estimated_cost', 'vehicle_type_needed',
            'status', 'transporter', 'transporter_name', 'created_at'
        ]

    def get_transporter_name(self, obj):
        if obj.transporter:
            prof = getattr(obj.transporter, 'user_profile', None)
            return prof.full_name if prof and prof.full_name else obj.transporter.username
        return None


class TransportRequestDetailSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    farmer_name = serializers.SerializerMethodField()
    transporter_name = serializers.SerializerMethodField()
    transporter_phone = serializers.CharField(source='transporter.phone', read_only=True)

    class Meta:
        model = TransportRequest
        fields = [
            'id', 'order', 'order_number', 'requester', 'buyer_name',
            'farmer_name', 'transporter', 'transporter_name', 'transporter_phone',
            'pickup_address', 'pickup_city', 'drop_address', 'drop_city',
            'estimated_distance_km', 'estimated_cost', 'final_charge',
            'vehicle_type_needed', 'status', 'tracking_notes',
            'scheduled_pickup', 'delivered_at', 'created_at', 'updated_at'
        ]

    def get_buyer_name(self, obj):
        buyer = obj.order.buyer
        prof = getattr(buyer, 'user_profile', None)
        return prof.full_name if prof and prof.full_name else buyer.username

    def get_farmer_name(self, obj):
        farmer = obj.order.farmer
        prof = getattr(farmer, 'user_profile', None)
        return prof.full_name if prof and prof.full_name else farmer.username

    def get_transporter_name(self, obj):
        if obj.transporter:
            prof = getattr(obj.transporter, 'user_profile', None)
            return prof.full_name if prof and prof.full_name else obj.transporter.username
        return "Unassigned"


class TransportRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportRequest
        fields = [
            'id', 'order', 'pickup_address', 'pickup_city',
            'drop_address', 'drop_city', 'estimated_distance_km',
            'estimated_cost', 'vehicle_type_needed', 'scheduled_pickup'
        ]

    def validate_order(self, value):
        user = self.context['request'].user
        if not (getattr(user, 'is_admin_user', False) or user.is_superuser):
            if value.buyer != user and value.farmer != user:
                raise serializers.ValidationError("You can only book transport for orders where you are the buyer or farmer.")
        if hasattr(value, 'transport_request'):
            raise serializers.ValidationError("A transport request already exists for this order.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['requester'] = user
        return super().create(validated_data)


class TransportStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TransportStatus.choices)
    tracking_notes = serializers.CharField(required=False, allow_blank=True)
    final_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
