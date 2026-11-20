from django.db import models
from django.conf import settings
import uuid


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Farmer Confirmation'
    CONFIRMED = 'confirmed', 'Confirmed by Farmer'
    PROCESSING = 'processing', 'Processing & Packing'
    DISPATCHED = 'dispatched', 'Dispatched / In Transit'
    DELIVERED = 'delivered', 'Delivered & Completed'
    CANCELLED = 'cancelled', 'Cancelled by Buyer'
    REJECTED = 'rejected', 'Rejected by Farmer'


class PaymentMethod(models.TextChoices):
    COD = 'cod', 'Cash on Delivery (Safe Offline)'
    BANK_TRANSFER = 'bank_transfer', 'Direct Bank Transfer / NEFT'
    OTHER = 'other', 'Other Offline Payment'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Payment Pending'
    COMPLETED = 'completed', 'Payment Received'
    REFUNDED = 'refunded', 'Refunded'
    FAILED = 'failed', 'Payment Failed'


class Order(models.Model):
    """
    Direct Agricultural Purchase Order placed by a Buyer to a Farmer.
    Uses pessimistic row-locking on crop inventory to prevent overselling.
    """
    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='buyer_orders',
        help_text="Buyer who placed the order"
    )
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='farmer_orders',
        help_text="Farmer who supplies the harvest"
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total order cost in INR (₹)")
    status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True
    )
    delivery_address = models.TextField(help_text="Full destination delivery address")
    delivery_city = models.CharField(max_length=100, help_text="Destination city")
    delivery_state = models.CharField(max_length=100, help_text="Destination state")
    delivery_pincode = models.CharField(max_length=10, blank=True, help_text="Postal PIN code")
    contact_phone = models.CharField(max_length=20, help_text="Contact number for delivery coordination")
    notes = models.TextField(blank=True, help_text="Special delivery instructions or farmer notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders_order'
        verbose_name = 'Crop Order'
        verbose_name_plural = 'Crop Orders'
        ordering = ['-created_at']

    @classmethod
    def generate_order_number(cls):
        return f"FC-{uuid.uuid4().hex[:8].upper()}"

    def __str__(self):
        return f"Order #{self.order_number} - ₹{self.total_amount} ({self.get_status_display()})"


class OrderItem(models.Model):
    """
    Line item linking an Order to a specific Crop listing.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    crop_listing = models.ForeignKey(
        'crops.Crop',
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    crop_title = models.CharField(max_length=150, help_text="Snapshot of crop name at purchase")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity ordered")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Agreed unit price in ₹")
    unit = models.CharField(max_length=20, help_text="Measurement unit (e.g. quintal, kg)")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, help_text="Line item subtotal")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders_orderitem'
        verbose_name = 'Order Line Item'
        verbose_name_plural = 'Order Line Items'

    def __str__(self):
        return f"{self.crop_title} ({self.quantity} {self.unit}) @ ₹{self.unit_price}"


class Payment(models.Model):
    """
    Safe offline payment record tracking Cash-on-Delivery or Direct Transfers.
    Does not collect card numbers or simulate live gateways.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='payment'
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.COD
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Optional bank reference or offline receipt number"
    )
    paid_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when payment was collected/verified")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders_payment'
        verbose_name = 'Order Payment'
        verbose_name_plural = 'Order Payments'

    def __str__(self):
        return f"Payment for #{self.order.order_number}: ₹{self.amount} ({self.get_payment_status_display()})"


class NegotiationStatus(models.TextChoices):
    PENDING = 'pending', 'Offer Submitted by Buyer'
    ACCEPTED = 'accepted', 'Offer Accepted by Farmer'
    REJECTED = 'rejected', 'Offer Rejected by Farmer'
    COUNTERED = 'countered', 'Counter-Offer Proposed by Farmer'
    BUYER_REJECTED = 'buyer_rejected', 'Counter Rejected by Buyer'
    CONVERTED = 'converted', 'Converted to Confirmed Order'


class PriceNegotiation(models.Model):
    """
    Price negotiation offer and counter-offer between a Buyer and a Farmer.
    Mapped to existing database table 'pricing_buyeroffer'.
    """
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_offers',
        help_text="Buyer who made the offer"
    )
    listing = models.ForeignKey(
        'crops.Crop',
        on_delete=models.CASCADE,
        related_name='offers',
        help_text="Target crop listing being negotiated"
    )
    offered_price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Buyer proposed price per unit in ₹"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Desired purchase quantity"
    )
    total_offered_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total proposed transaction value"
    )
    counter_price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Farmer proposed counter price per unit in ₹"
    )
    status = models.CharField(
        max_length=20,
        choices=NegotiationStatus.choices,
        default=NegotiationStatus.PENDING,
        db_index=True
    )
    message = models.TextField(blank=True, help_text="Buyer proposition note")
    farmer_notes = models.TextField(blank=True, help_text="Farmer response or counter-offer reasoning")
    converted_order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='from_negotiation',
        help_text="Confirmed Order resulting from this negotiation"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_buyeroffer'
        verbose_name = 'Price Negotiation Offer'
        verbose_name_plural = 'Price Negotiation Offers'
        ordering = ['-created_at']

    @property
    def farmer(self):
        return self.listing.farmer

    @property
    def farmer_listed_price(self):
        return self.listing.price_per_unit

    @property
    def final_agreed_price(self):
        if self.counter_price_per_unit:
            return self.counter_price_per_unit
        return self.offered_price_per_unit

    @property
    def crop_name(self):
        return self.listing.crop_name

    def __str__(self):
        return f"Offer #{self.id} on {self.crop_name}: ₹{self.offered_price_per_unit}/{self.listing.unit} by {self.buyer.username} ({self.get_status_display()})"
