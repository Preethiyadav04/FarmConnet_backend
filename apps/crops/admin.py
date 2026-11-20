from django.contrib import admin
from .models import Category, Crop, MandiPrice


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ('crop_name', 'farmer', 'category', 'price_per_unit', 'unit', 'quantity_available', 'status', 'location_city', 'created_at')
    list_filter = ('status', 'category', 'grade_quality', 'unit', 'location_state')
    search_fields = ('crop_name', 'variety', 'farmer__username', 'location_city')
    date_hierarchy = 'created_at'


@admin.register(MandiPrice)
class MandiPriceAdmin(admin.ModelAdmin):
    list_display = ('crop_name', 'market_name', 'state', 'modal_price', 'price_unit', 'price_date', 'data_source')
    list_filter = ('state', 'price_date')
    search_fields = ('crop_name', 'market_name', 'district', 'state')
    date_hierarchy = 'price_date'
