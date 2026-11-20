from django.db import models
from django.conf import settings


class NotificationType(models.TextChoices):
    ORDER = 'order', 'Order Update'
    NEGOTIATION = 'negotiation', 'Price Negotiation'
    LOGISTICS = 'logistics', 'Logistics & Shipment'
    PAYMENT = 'payment', 'Payment Update'
    SYSTEM = 'system', 'System Notification'


class Notification(models.Model):
    """
    User notification record for platform alerts, status updates, and messages.
    Mapped to existing database table 'notifications_notification'.
    """
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="Recipient user"
    )
    title = models.CharField(max_length=200, help_text="Short notification subject")
    message = models.TextField(help_text="Notification detailed message body")
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        db_index=True
    )
    is_read = models.BooleanField(default=False, db_index=True)
    action_url = models.CharField(max_length=255, blank=True, help_text="Frontend routing link")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_notification'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        read_badge = "✓" if self.is_read else "●"
        return f"[{read_badge}] {self.recipient.username}: {self.title}"


def send_notification(recipient, title, message, notification_type=NotificationType.SYSTEM, action_url=""):
    """
    Helper utility to reliably create and dispatch user notifications.
    Fails safely so core business transactions are never aborted by notification errors.
    """
    if not recipient:
        return None
    try:
        return Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            action_url=action_url
        )
    except Exception:
        return None
