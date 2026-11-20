from django.contrib import admin
from .models import Order, OrderItem, Payment, PriceNegotiation


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['crop_listing', 'crop_title', 'quantity', 'unit', 'unit_price', 'subtotal']


class PaymentInline(admin.StackedInline):
    model = Payment
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'buyer', 'farmer', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['order_number', 'buyer__username', 'farmer__username', 'delivery_city']
    readonly_fields = ['order_number', 'created_at', 'updated_at']
    inlines = [OrderItemInline, PaymentInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'crop_title', 'quantity', 'unit', 'unit_price', 'subtotal']
    search_fields = ['order__order_number', 'crop_title']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'payment_method', 'payment_status', 'amount', 'paid_at']
    list_filter = ['payment_method', 'payment_status']
    search_fields = ['order__order_number', 'transaction_reference']


@admin.register(PriceNegotiation)
class PriceNegotiationAdmin(admin.ModelAdmin):
    list_display = ['id', 'buyer', 'listing', 'offered_price_per_unit', 'counter_price_per_unit', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['buyer__username', 'listing__crop_name']
