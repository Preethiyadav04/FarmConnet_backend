from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    FARMER = 'farmer', 'Farmer'
    BUYER = 'buyer', 'Buyer'
    TRANSPORTER = 'transporter', 'Transporter'
    ADMIN = 'admin', 'Admin'


class User(AbstractUser):
    """
    Custom User Model for FarmConnect supporting distinct roles:
    Farmer, Buyer, Transporter, and Admin.
    Aligned with the persistent MySQL farmconnect_db schema.
    """
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.BUYER,
        db_index=True,
        help_text="Primary platform role determining permissions and dashboard access."
    )
    phone = models.CharField(max_length=15, default='', blank=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="Verification status for KYC/identity checks performed by Admin."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_farmer(self):
        return (self.role or '').lower() == 'farmer'

    @property
    def is_buyer(self):
        return (self.role or '').lower() == 'buyer'

    @property
    def is_transporter(self):
        return (self.role or '').lower() == 'transporter'

    @property
    def is_admin_user(self):
        return (self.role or '').lower() == 'admin' or self.is_superuser or self.is_staff

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class UserProfile(models.Model):
    """General contact and location profile for all users."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='user_profile'
    )
    full_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, db_index=True)
    pincode = models.CharField(max_length=10, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"UserProfile: {self.user.username} ({self.full_name or 'No name'})"


class FarmerProfile(models.Model):
    """Extended profile information specific to Farmers."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='farmer_profile'
    )
    farm_name = models.CharField(max_length=150, blank=True)
    farm_size_acres = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.00,
        help_text="Cultivable land area in acres"
    )
    soil_type = models.CharField(max_length=100, blank=True)
    farming_experience_years = models.PositiveIntegerField(default=0)
    organic_certified = models.BooleanField(default=False)
    primary_crops = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FarmerProfile: {self.user.username} ({self.farm_name or 'No farm name'})"


class BuyerProfile(models.Model):
    """Extended profile information specific to Buyers."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='buyer_profile'
    )
    business_name = models.CharField(max_length=150, blank=True)
    buyer_type = models.CharField(max_length=30, blank=True)
    gst_number = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BuyerProfile: {self.user.username} ({self.business_name or 'Personal'})"


class TransporterProfile(models.Model):
    """Extended profile information specific to Transporters."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='transporter_profile'
    )
    vehicle_type = models.CharField(max_length=40, blank=True)
    vehicle_number = models.CharField(max_length=50, blank=True)
    driving_license = models.CharField(max_length=50, blank=True)
    max_capacity_tons = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text="Maximum cargo payload capacity in metric tons."
    )
    service_radius_km = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"TransporterProfile: {self.user.username} - {self.vehicle_number}"
