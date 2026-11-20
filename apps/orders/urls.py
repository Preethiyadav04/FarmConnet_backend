from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, PriceNegotiationViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'negotiations', PriceNegotiationViewSet, basename='negotiation')

urlpatterns = [
    path('', include(router.urls)),
]
