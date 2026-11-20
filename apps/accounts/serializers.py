from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import UserRole, UserProfile, FarmerProfile, BuyerProfile, TransporterProfile

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT Token Serializer that attaches user profile claims to the JWT payload
    and enriches the login response with essential user metadata.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['role'] = user.role
        token['is_verified'] = user.is_verified
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user_profile = getattr(self.user, 'user_profile', None)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'full_name': user_profile.full_name if user_profile else f"{self.user.first_name} {self.user.last_name}".strip(),
            'role': self.user.role,
            'phone': self.user.phone,
            'city': user_profile.city if user_profile else None,
            'state': user_profile.state if user_profile else None,
            'is_verified': self.user.is_verified,
        }
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'full_name', 'avatar', 'address', 'city', 'state', 'pincode', 'bio', 'created_at']
        read_only_fields = ['id', 'created_at']


class FarmerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmerProfile
        fields = ['id', 'farm_name', 'farm_size_acres', 'soil_type', 'farming_experience_years', 'organic_certified', 'primary_crops', 'created_at']
        read_only_fields = ['id', 'created_at']


class BuyerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerProfile
        fields = ['id', 'business_name', 'buyer_type', 'gst_number', 'created_at']
        read_only_fields = ['id', 'created_at']


class TransporterProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransporterProfile
        fields = ['id', 'vehicle_type', 'vehicle_number', 'driving_license', 'max_capacity_tons', 'service_radius_km', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer(read_only=True)
    farmer_profile = FarmerProfileSerializer(read_only=True)
    buyer_profile = BuyerProfileSerializer(read_only=True)
    transporter_profile = TransporterProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'is_verified', 'created_at',
            'user_profile', 'farmer_profile', 'buyer_profile', 'transporter_profile'
        ]
        read_only_fields = ['id', 'is_verified', 'created_at']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    full_name = serializers.CharField(write_only=True, required=False, default='')
    address = serializers.CharField(write_only=True, required=False, default='')
    city = serializers.CharField(write_only=True, required=False, default='')
    state = serializers.CharField(write_only=True, required=False, default='')
    pincode = serializers.CharField(write_only=True, required=False, default='')

    # Role-specific profile fields (optional upon initial registration)
    farm_name = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    farm_size_acres = serializers.DecimalField(write_only=True, required=False, max_digits=8, decimal_places=2, default=0.00)
    business_name = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    buyer_type = serializers.CharField(write_only=True, required=False, allow_blank=True, default='individual')
    gst_number = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    vehicle_type = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    vehicle_number = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')
    max_capacity_tons = serializers.DecimalField(write_only=True, required=False, max_digits=6, decimal_places=2, default=0.00)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone',
            'full_name', 'address', 'city', 'state', 'pincode',
            'farm_name', 'farm_size_acres',
            'business_name', 'buyer_type', 'gst_number',
            'vehicle_type', 'vehicle_number', 'max_capacity_tons'
        ]

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        if 'role' in data and isinstance(data['role'], str):
            data['role'] = data['role'].lower()
        return super().to_internal_value(data)

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value.strip().lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Password fields do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        full_name = validated_data.pop('full_name', '')
        address = validated_data.pop('address', '')
        city = validated_data.pop('city', '')
        state = validated_data.pop('state', '')
        pincode = validated_data.pop('pincode', '')

        # Pop role profile fields
        farm_name = validated_data.pop('farm_name', '')
        farm_size_acres = validated_data.pop('farm_size_acres', 0.00)
        business_name = validated_data.pop('business_name', '')
        buyer_type = validated_data.pop('buyer_type', 'individual')
        gst_number = validated_data.pop('gst_number', '')
        vehicle_type = validated_data.pop('vehicle_type', '')
        vehicle_number = validated_data.pop('vehicle_number', '')
        max_capacity_tons = validated_data.pop('max_capacity_tons', 0.00)

        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()

        # Update the automatically created UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if full_name:
            profile.full_name = full_name
        if address:
            profile.address = address
        if city:
            profile.city = city
        if state:
            profile.state = state
        if pincode:
            profile.pincode = pincode
        profile.save()

        # Populate role-specific profile
        role = (user.role or '').lower()
        if role == 'farmer':
            fp, _ = FarmerProfile.objects.get_or_create(user=user)
            if farm_name:
                fp.farm_name = farm_name
            if farm_size_acres:
                fp.farm_size_acres = farm_size_acres
            fp.save()
        elif role == 'buyer':
            bp, _ = BuyerProfile.objects.get_or_create(user=user)
            if business_name:
                bp.business_name = business_name
            if buyer_type:
                bp.buyer_type = buyer_type
            if gst_number:
                bp.gst_number = gst_number
            bp.save()
        elif role == 'transporter':
            tp, _ = TransporterProfile.objects.get_or_create(user=user)
            if vehicle_type:
                tp.vehicle_type = vehicle_type
            if vehicle_number:
                tp.vehicle_number = vehicle_number
            if max_capacity_tons:
                tp.max_capacity_tons = max_capacity_tons
            tp.save()

        try:
            user.refresh_from_db()
        except Exception:
            pass
        return user

    def to_representation(self, instance):
        try:
            instance.refresh_from_db()
        except Exception:
            pass
        return UserSerializer(instance, context=self.context).data
