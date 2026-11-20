from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    RegisterView,
    UserProfileView,
    RoleProfileUpdateView,
    HealthCheckView,
    AdminUserViewSet,
)

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='user')

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='api-health'),
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='auth-login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/profile/', UserProfileView.as_view(), name='user-profile'),
    path('auth/profile/role/', RoleProfileUpdateView.as_view(), name='role-profile-update'),
    path('', include(router.urls)),
]
