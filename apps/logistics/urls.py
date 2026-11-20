from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransportRequestViewSet

router = DefaultRouter()
router.register(r'logistics', TransportRequestViewSet, basename='logistics')

urlpatterns = [
    path('', include(router.urls)),
]
