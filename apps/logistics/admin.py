from django.contrib import admin
from .models import TransportRequest


@admin.register(TransportRequest)
class TransportRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order', 'requester', 'transporter', 'pickup_city',
        'drop_city', 'estimated_cost', 'status', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['order__order_number', 'pickup_city', 'drop_city', 'transporter__username']
    readonly_fields = ['created_at', 'updated_at']
