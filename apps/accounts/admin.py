from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, FarmerProfile, BuyerProfile, TransporterProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Contact & Location Profile'


class FarmerProfileInline(admin.StackedInline):
    model = FarmerProfile
    can_delete = False
    verbose_name_plural = 'Farmer Profile'


class BuyerProfileInline(admin.StackedInline):
    model = BuyerProfile
    can_delete = False
    verbose_name_plural = 'Buyer Profile'


class TransporterProfileInline(admin.StackedInline):
    model = TransporterProfile
    can_delete = False
    verbose_name_plural = 'Transporter Profile'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'phone', 'is_verified', 'is_staff')
    list_filter = ('role', 'is_verified', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('FarmConnect Role & Verification', {
            'fields': ('role', 'phone', 'is_verified')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('FarmConnect Role & Verification', {
            'fields': ('role', 'phone', 'is_verified')
        }),
    )
    inlines = [UserProfileInline, FarmerProfileInline, BuyerProfileInline, TransporterProfileInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'city', 'state', 'pincode', 'created_at')
    search_fields = ('user__username', 'full_name', 'city', 'state')


@admin.register(FarmerProfile)
class FarmerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'farm_name', 'farm_size_acres', 'primary_crops', 'organic_certified', 'created_at')
    list_filter = ('organic_certified',)
    search_fields = ('user__username', 'farm_name', 'primary_crops')


@admin.register(BuyerProfile)
class BuyerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'business_name', 'buyer_type', 'gst_number', 'created_at')
    search_fields = ('user__username', 'business_name', 'gst_number')


@admin.register(TransporterProfile)
class TransporterProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'vehicle_type', 'vehicle_number', 'driving_license', 'max_capacity_tons', 'service_radius_km', 'created_at')
    list_filter = ('vehicle_type',)
    search_fields = ('user__username', 'vehicle_number', 'driving_license')
