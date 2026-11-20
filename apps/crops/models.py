from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Category(models.Model):
    """
    Produce / Crop category (e.g. Grains, Vegetables, Fruits, Pulses, Spices, Oilseeds).
    """
    name = models.CharField(max_length=100, unique=True, help_text="Category name (e.g. Vegetables)")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, default='leaf', help_text="Lucide icon identifier")
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Whether this category is active in the catalog")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketplace_cropcategory'
        verbose_name = 'Crop Category'
        verbose_name_plural = 'Crop Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CropUnit(models.TextChoices):
    KG = 'kg', 'Kilogram (kg)'
    QUINTAL = 'quintal', 'Quintal (100 kg)'
    TON = 'ton', 'Metric Ton (1000 kg)'


class CropGrade(models.TextChoices):
    GRADE_A = 'Grade A', 'Grade A (Export / Premium)'
    GRADE_B = 'Grade B', 'Grade B (Standard Commercial)'
    GRADE_C = 'Grade C', 'Grade C (Bulk / Processing)'


class CropStatus(models.TextChoices):
    ACTIVE = 'active', 'Available'
    UNAVAILABLE = 'unavailable', 'Unavailable'
    SOLD_OUT = 'sold_out', 'Sold Out'
    DRAFT = 'draft', 'Draft'


class Crop(models.Model):
    """
    Individual crop listing posted by a registered Farmer.
    """
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='crops',
        help_text="Farmer who owns and listed this crop"
    )
    crop_name = models.CharField(max_length=120, db_index=True, help_text="Name of the crop (e.g. Sharbati Wheat)")
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='crops',
        help_text="Produce category"
    )
    variety = models.CharField(max_length=100, blank=True, help_text="Crop cultivar or variety (e.g. Lokwan, Hybrid)")
    description = models.TextField(blank=True, help_text="Detailed crop description, farming methods, quality notes")
    grade_quality = models.CharField(
        max_length=20,
        choices=CropGrade.choices,
        default=CropGrade.GRADE_A,
        help_text="Quality classification"
    )
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Selling price per selected unit in INR (₹)"
    )
    unit = models.CharField(
        max_length=20,
        choices=CropUnit.choices,
        default=CropUnit.QUINTAL,
        help_text="Measurement unit"
    )
    quantity_available = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Remaining unsold stock quantity"
    )
    minimum_order_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1.00,
        help_text="Minimum batch order threshold"
    )
    harvest_date = models.DateField(null=True, blank=True, help_text="Date when crop was harvested")
    expiry_date = models.DateField(null=True, blank=True, help_text="Available until date / shelf life")
    location_city = models.CharField(max_length=100, db_index=True, help_text="City or Taluka of farm")
    location_state = models.CharField(max_length=100, db_index=True, help_text="State of farm")
    location_pincode = models.CharField(max_length=10, blank=True, help_text="Postal PIN code")
    image = models.ImageField(upload_to='crops/', blank=True, null=True, help_text="Primary photograph of harvest")
    status = models.CharField(
        max_length=20,
        choices=CropStatus.choices,
        default=CropStatus.ACTIVE,
        db_index=True,
        help_text="Current availability status"
    )
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketplace_croplisting'
        verbose_name = 'Crop Listing'
        verbose_name_plural = 'Crop Listings'
        ordering = ['-created_at']

    @property
    def is_available(self):
        return self.status == CropStatus.ACTIVE and self.quantity_available > 0

    @property
    def location(self):
        parts = [self.location_city, self.location_state]
        return ", ".join(p for p in parts if p)

    def __str__(self):
        return f"{self.crop_name} - ₹{self.price_per_unit}/{self.unit} ({self.farmer.username})"


class MandiPrice(models.Model):
    """
    Regional APMC / Mandi market price benchmark data.
    Provides benchmark comparison data for buyers and farmers.
    Clearly labeled with source, date, and verified demonstration tag.
    """
    crop_name = models.CharField(max_length=100, db_index=True, help_text="Standardized commodity name (e.g. Wheat)")
    market_name = models.CharField(max_length=120, db_index=True, help_text="APMC Mandi yard name (e.g. Nashik Mandi)")
    district = models.CharField(max_length=100, blank=True, help_text="District")
    state = models.CharField(max_length=100, db_index=True, help_text="State")
    min_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Lowest recorded transaction rate")
    max_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Highest recorded transaction rate")
    modal_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Most frequent trading modal price")
    price_unit = models.CharField(max_length=30, default='₹ / Quintal', help_text="Trading rate unit")
    price_date = models.DateField(db_index=True, help_text="Date of market price capture")
    data_source = models.CharField(
        max_length=120,
        default='Agmarknet / Mandi Benchmark (Sample Market Data)',
        help_text="Official source reference or demonstration label"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_marketprice'
        verbose_name = 'Mandi Market Price'
        verbose_name_plural = 'Mandi Market Prices'
        ordering = ['-price_date', 'crop_name']

    def __str__(self):
        return f"{self.crop_name} @ {self.market_name} ({self.price_date}) - Modal: ₹{self.modal_price}"
