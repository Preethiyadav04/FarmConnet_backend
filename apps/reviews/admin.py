from django.contrib import admin
from .models import Review, Favorite, Complaint


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating', 'buyer', 'farmer', 'order', 'crop_listing', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['buyer__username', 'farmer__username', 'comment', 'order__order_number']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['id', 'buyer', 'crop_listing', 'created_at']
    search_fields = ['buyer__username', 'crop_listing__crop_name']


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'user', 'order', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description', 'user__username', 'order__order_number']
