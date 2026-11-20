from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Review(models.Model):
    """
    Farmer Reviews & Ratings submitted by Buyers after successful order delivery.
    Mapped to existing database table 'reviews_review'.
    """
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_reviews',
        help_text="Buyer who authored the review"
    )
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_reviews',
        help_text="Farmer receiving the rating and review"
    )
    crop_listing = models.ForeignKey(
        'crops.Crop',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
        help_text="Optional reference to the purchased crop"
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
        help_text="Completed order this review is based upon"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating score from 1 (poor) to 5 (excellent)"
    )
    comment = models.TextField(help_text="Written feedback or testimonial")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews_review'
        verbose_name = 'Farmer Review'
        verbose_name_plural = 'Farmer Reviews'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating}★ Review by {self.buyer.username} for {self.farmer.username}"


class Favorite(models.Model):
    """
    Buyer bookmarked favorite crop listings.
    Mapped to existing database table 'reviews_favorite'.
    """
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
        help_text="Buyer who bookmarked the crop"
    )
    crop_listing = models.ForeignKey(
        'crops.Crop',
        on_delete=models.CASCADE,
        related_name='favorited_by',
        help_text="Favorited crop listing"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews_favorite'
        verbose_name = 'Favorite Crop'
        verbose_name_plural = 'Favorite Crops'
        ordering = ['-created_at']
        unique_together = ('buyer', 'crop_listing')

    def __str__(self):
        return f"{self.buyer.username} favorited {self.crop_listing.crop_name}"


class Complaint(models.Model):
    """
    Dispute and complaint ticketing between parties.
    Mapped to existing database table 'reviews_complaint'.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaints'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='complaints'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=30, default='pending', db_index=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews_complaint'
        verbose_name = 'Order Complaint / Dispute'
        verbose_name_plural = 'Order Complaints & Disputes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Complaint #{self.id}: {self.title} ({self.status})"
