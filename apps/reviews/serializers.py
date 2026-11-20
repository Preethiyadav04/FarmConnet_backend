from rest_framework import serializers
from .models import Review, Favorite, Complaint
from apps.orders.models import Order, OrderStatus


class ReviewSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()
    farmer_name = serializers.SerializerMethodField()
    crop_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'order', 'order_number', 'buyer', 'buyer_name',
            'farmer', 'farmer_name', 'crop_listing', 'crop_name',
            'rating', 'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'buyer', 'farmer', 'crop_listing', 'created_at', 'updated_at']

    def get_buyer_name(self, obj):
        prof = getattr(obj.buyer, 'user_profile', None)
        return prof.full_name if prof and prof.full_name else obj.buyer.username

    def get_farmer_name(self, obj):
        fprof = getattr(obj.farmer, 'farmer_profile', None)
        if fprof and fprof.farm_name:
            return fprof.farm_name
        prof = getattr(obj.farmer, 'user_profile', None)
        return prof.full_name if prof and prof.full_name else obj.farmer.username

    def get_crop_name(self, obj):
        if obj.crop_listing:
            return obj.crop_listing.crop_name
        return None

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        return value

    def validate_order(self, order):
        request = self.context.get('request')
        user = request.user if request else None

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required to review an order.")

        # Non-admin buyers must own the order
        if not (getattr(user, 'is_admin_user', False) or user.is_superuser):
            if order.buyer != user:
                raise serializers.ValidationError("You can only review orders that you placed as a buyer.")

        # Order must be delivered/completed
        if order.status != OrderStatus.DELIVERED:
            raise serializers.ValidationError(
                f"Reviews can only be submitted after an order has been successfully delivered. Current status: '{order.status}'."
            )

        # Duplicate check: check if review for this order already exists
        review_query = Review.objects.filter(order=order)
        if self.instance:
            review_query = review_query.exclude(pk=self.instance.pk)
        if review_query.exists():
            raise serializers.ValidationError("A review has already been submitted for this order. Duplicate reviews are not allowed.")

        return order

    def create(self, validated_data):
        request = self.context.get('request')
        order = validated_data['order']
        buyer = request.user

        # Automatically bind farmer and crop from order
        farmer = order.farmer
        first_item = order.items.first()
        crop_listing = first_item.crop_listing if first_item else None

        validated_data['buyer'] = buyer
        validated_data['farmer'] = farmer
        validated_data['crop_listing'] = crop_listing

        return super().create(validated_data)


class FavoriteSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source='crop_listing.crop_name', read_only=True)
    crop_price = serializers.DecimalField(source='crop_listing.price_per_unit', max_digits=10, decimal_places=2, read_only=True)
    crop_unit = serializers.CharField(source='crop_listing.unit', read_only=True)
    farmer_name = serializers.CharField(source='crop_listing.farmer.username', read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'buyer', 'crop_listing', 'crop_name', 'crop_price', 'crop_unit', 'farmer_name', 'created_at']
        read_only_fields = ['id', 'buyer', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['buyer'] = user
        return super().create(validated_data)
