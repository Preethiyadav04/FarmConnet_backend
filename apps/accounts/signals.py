from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile, FarmerProfile, BuyerProfile, TransporterProfile


@receiver(post_save, sender=User)
def create_or_update_user_profiles(sender, instance, created, **kwargs):
    """
    Automatically creates the UserProfile and role-specific profiles
    upon User registration.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
        role = (instance.role or '').lower()
        if role == 'farmer':
            FarmerProfile.objects.get_or_create(user=instance)
        elif role == 'buyer':
            BuyerProfile.objects.get_or_create(user=instance)
        elif role == 'transporter':
            TransporterProfile.objects.get_or_create(user=instance)
