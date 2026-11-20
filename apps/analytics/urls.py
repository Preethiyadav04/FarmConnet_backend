from django.urls import path
from .views import (
    DashboardAnalyticsView,
    FarmerAnalyticsView,
    BuyerAnalyticsView,
    TransporterAnalyticsView,
    AdminAnalyticsView
)

urlpatterns = [
    path('analytics/dashboard/', DashboardAnalyticsView.as_view(), name='analytics-dashboard'),
    path('analytics/farmer/', FarmerAnalyticsView.as_view(), name='analytics-farmer'),
    path('analytics/buyer/', BuyerAnalyticsView.as_view(), name='analytics-buyer'),
    path('analytics/transporter/', TransporterAnalyticsView.as_view(), name='analytics-transporter'),
    path('analytics/admin/', AdminAnalyticsView.as_view(), name='analytics-admin'),
]
