from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, CropViewSet, MandiPriceViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'crops', CropViewSet, basename='crop')
router.register(r'mandi-prices', MandiPriceViewSet, basename='mandi-price')

urlpatterns = [
    path('', include(router.urls)),
]
