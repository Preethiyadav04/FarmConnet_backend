from rest_framework import serializers
from .models import Category, Crop, MandiPrice
from apps.accounts.models import FarmerProfile, UserProfile


class CategorySerializer(serializers.ModelSerializer):
    crops_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'icon',
            'image', 'is_active', 'crops_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'crops_count', 'created_at', 'updated_at']

    def get_crops_count(self, obj):
        return obj.crops.filter(status='active').count()


class FarmerPublicSerializer(serializers.Serializer):
    """Safe public representation of a farmer. Never exposes private contact info or earnings."""
    id = serializers.IntegerField(source='user.id')
    username = serializers.CharField(source='user.username')
    full_name = serializers.SerializerMethodField()
    farm_name = serializers.CharField(read_only=True)
    farm_size_acres = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    location = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField(source='user.is_verified')
    organic_certified = serializers.BooleanField(read_only=True)

    def get_full_name(self, obj):
        profile = getattr(obj.user, 'user_profile', None)
        if profile and profile.full_name:
            return profile.full_name
        return obj.user.get_full_name() or obj.user.username

    def get_location(self, obj):
        profile = getattr(obj.user, 'user_profile', None)
        if profile and (profile.city or profile.state):
            parts = [profile.city, profile.state]
            return ", ".join(p for p in parts if p)
        return "India"


class CropListSerializer(serializers.ModelSerializer):
    """Optimized serializer for the Buyer Marketplace catalog listing."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    farmer_name = serializers.SerializerMethodField()
    farmer_verified = serializers.BooleanField(source='farmer.is_verified', read_only=True)
    location = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Crop
        fields = [
            'id', 'crop_name', 'variety', 'category', 'category_name', 'category_slug',
            'grade_quality', 'price_per_unit', 'unit', 'quantity_available',
            'minimum_order_quantity', 'location_city', 'location_state', 'location',
            'image', 'status', 'is_available', 'is_featured', 'farmer_name',
            'farmer_verified', 'harvest_date', 'expiry_date', 'created_at'
        ]

    def get_farmer_name(self, obj):
        farmer_profile = getattr(obj.farmer, 'farmer_profile', None)
        if farmer_profile and farmer_profile.farm_name:
            return farmer_profile.farm_name
        user_profile = getattr(obj.farmer, 'user_profile', None)
        if user_profile and user_profile.full_name:
            return user_profile.full_name
        return obj.farmer.username


class CropDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single Crop view with farmer profile and benchmark comparison."""
    category = CategorySerializer(read_only=True)
    farmer_info = serializers.SerializerMethodField()
    location = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    mandi_benchmark = serializers.SerializerMethodField()

    class Meta:
        model = Crop
        fields = [
            'id', 'crop_name', 'variety', 'category', 'description',
            'grade_quality', 'price_per_unit', 'unit', 'quantity_available',
            'minimum_order_quantity', 'harvest_date', 'expiry_date',
            'location_city', 'location_state', 'location_pincode', 'location',
            'image', 'status', 'is_available', 'is_featured', 'views_count',
            'farmer_info', 'mandi_benchmark', 'created_at', 'updated_at'
        ]

    def get_farmer_info(self, obj):
        farmer_profile = getattr(obj.farmer, 'farmer_profile', None)
        if farmer_profile:
            return FarmerPublicSerializer(farmer_profile).data
        return {
            'id': obj.farmer.id,
            'username': obj.farmer.username,
            'is_verified': obj.farmer.is_verified,
            'farm_name': 'Farm'
        }

    def get_mandi_benchmark(self, obj):
        """Finds matching regional benchmark prices to assist buyer/farmer price comparison."""
        benchmarks = MandiPrice.objects.filter(
            crop_name__icontains=obj.crop_name.split()[0]
        ).order_by('-price_date')[:3]
        if benchmarks.exists():
            return MandiPriceSerializer(benchmarks, many=True).data
        return []


class CropCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer used by authenticated Farmers to add or update crop listings."""
    class Meta:
        model = Crop
        fields = [
            'id', 'crop_name', 'category', 'variety', 'description',
            'grade_quality', 'price_per_unit', 'unit', 'quantity_available',
            'minimum_order_quantity', 'harvest_date', 'expiry_date',
            'location_city', 'location_state', 'location_pincode', 'image',
            'status'
        ]
        read_only_fields = ['id']

    def validate_price_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price per unit must be greater than zero.")
        return value

    def validate_quantity_available(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity available cannot be negative.")
        return value

    def validate(self, attrs):
        qty = attrs.get('quantity_available')
        min_qty = attrs.get('minimum_order_quantity')
        if qty is not None and min_qty is not None and min_qty > qty:
            raise serializers.ValidationError({
                "minimum_order_quantity": "Minimum order quantity cannot exceed available stock quantity."
            })
        return attrs

    def create(self, validated_data):
        # Automatically assign the authenticated farmer
        request = self.context.get('request')
        validated_data['farmer'] = request.user

        # Auto-fill location if not explicitly provided
        if not validated_data.get('location_city') or not validated_data.get('location_state'):
            user_profile = getattr(request.user, 'user_profile', None)
            if user_profile:
                if not validated_data.get('location_city') and user_profile.city:
                    validated_data['location_city'] = user_profile.city
                if not validated_data.get('location_state') and user_profile.state:
                    validated_data['location_state'] = user_profile.state
                if not validated_data.get('location_pincode') and user_profile.pincode:
                    validated_data['location_pincode'] = user_profile.pincode

        return super().create(validated_data)


class MandiPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MandiPrice
        fields = [
            'id', 'crop_name', 'market_name', 'district', 'state',
            'min_price', 'max_price', 'modal_price', 'price_unit',
            'price_date', 'data_source', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        min_p = attrs.get('min_price')
        max_p = attrs.get('max_price')
        modal_p = attrs.get('modal_price')
        if min_p and max_p and min_p > max_p:
            raise serializers.ValidationError({"min_price": "Minimum price cannot be greater than maximum price."})
        if modal_p and min_p and max_p:
            if modal_p < min_p or modal_p > max_p:
                raise serializers.ValidationError({"modal_price": "Modal price must be within min and max price range."})
        return attrs
