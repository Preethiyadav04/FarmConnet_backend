from django.db import models
from django.conf import settings


class TransportStatus(models.TextChoices):
    REQUESTED = 'requested', 'Requested (Open for Transporters)'
    ACCEPTED = 'accepted', 'Accepted by Transporter'
    PICKED_UP = 'picked_up', 'Cargo Picked Up from Farm'
    IN_TRANSIT = 'in_transit', 'In Transit / On the Road'
    DELIVERED = 'delivered', 'Delivered to Destination'
    CANCELLED = 'cancelled', 'Transport Cancelled'


class TransportRequest(models.Model):
    """
    Logistics shipment dispatch request connecting orders to transporters.
    Mapped to existing database table 'logistics_transportrequest'.
    """
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='transport_request',
        help_text="Order being shipped"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transport_requests',
        help_text="Buyer or Farmer who requested the delivery service"
    )
    transporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_transports',
        help_text="Assigned commercial transporter"
    )
    pickup_address = models.TextField(help_text="Farm / Pickup dispatch point")
    pickup_city = models.CharField(max_length=100)
    drop_address = models.TextField(help_text="Destination delivery location")
    drop_city = models.CharField(max_length=100)
    estimated_distance_km = models.PositiveIntegerField(default=50, help_text="Estimated route distance in km")
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, help_text="Estimated freight charge in ₹")
    final_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final billed freight amount"
    )
    vehicle_type_needed = models.CharField(max_length=50, default='Standard Commercial Truck')
    status = models.CharField(
        max_length=30,
        choices=TransportStatus.choices,
        default=TransportStatus.REQUESTED,
        db_index=True
    )
    tracking_notes = models.TextField(blank=True, help_text="Status updates, checkpoint logs, or driver notes")
    scheduled_pickup = models.DateTimeField(null=True, blank=True, help_text="Scheduled pickup date/time")
    delivered_at = models.DateTimeField(null=True, blank=True, help_text="Actual delivery completion timestamp")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'logistics_transportrequest'
        verbose_name = 'Transport Request'
        verbose_name_plural = 'Transport Requests'
        ordering = ['-created_at']

    @property
    def buyer(self):
        return self.order.buyer

    @property
    def farmer(self):
        return self.order.farmer

    def __str__(self):
        return f"Transport for Order #{self.order.order_number} ({self.pickup_city} -> {self.drop_city}) [{self.get_status_display()}]"
