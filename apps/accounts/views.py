from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import UserProfile, FarmerProfile, BuyerProfile, TransporterProfile
from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    UserProfileSerializer,
    FarmerProfileSerializer,
    BuyerProfileSerializer,
    TransporterProfileSerializer,
)

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    """Obtain JWT access and refresh token pair with custom claims."""
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """Public registration endpoint for Farmers, Buyers, and Transporters."""
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class UserProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update the currently authenticated user's profile."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        user_profile, _ = UserProfile.objects.get_or_create(user=user)

        # Update base User fields if provided
        for field in ['first_name', 'last_name', 'phone']:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()

        # Update UserProfile fields if provided
        profile_fields = ['full_name', 'address', 'city', 'state', 'pincode', 'bio']
        for pf in profile_fields:
            if pf in request.data:
                setattr(user_profile, pf, request.data[pf])
        user_profile.save()

        return Response(UserSerializer(user).data)


class RoleProfileUpdateView(APIView):
    """Updates role-specific details for the authenticated user."""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        user = request.user
        role = (user.role or '').lower()
        if role == 'farmer':
            profile, _ = FarmerProfile.objects.get_or_create(user=user)
            serializer = FarmerProfileSerializer(profile, data=request.data, partial=True)
        elif role == 'buyer':
            profile, _ = BuyerProfile.objects.get_or_create(user=user)
            serializer = BuyerProfileSerializer(profile, data=request.data, partial=True)
        elif role == 'transporter':
            profile, _ = TransporterProfile.objects.get_or_create(user=user)
            serializer = TransporterProfileSerializer(profile, data=request.data, partial=True)
        else:
            return Response({"detail": "No role-specific profile for this role."}, status=status.HTTP_400_BAD_REQUEST)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HealthCheckView(APIView):
    """Public API health check endpoint to verify backend and database status."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from django.db import connection
        db_status = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
        except Exception as e:
            db_status = f"unreachable: {str(e)}"

        return Response({
            "status": "healthy",
            "service": "FarmConnect API",
            "database": db_status,
            "version": "1.0.0"
        })


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Administrative User Management ViewSet.
    - Only accessible by users with is_admin_user=True or is_superuser=True.
    - List, filter, retrieve, and toggle verification/active status.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if not (getattr(request.user, 'is_admin_user', False) or request.user.is_superuser):
            self.permission_denied(request, message="Administrative privileges required.")

    def get_queryset(self):
        qs = User.objects.select_related('user_profile', 'farmer_profile', 'buyer_profile', 'transporter_profile').all().order_by('-date_joined')
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role.lower())
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        verified = self.request.query_params.get('is_verified')
        if verified is not None:
            qs = qs.filter(is_verified=verified.lower() == 'true')
        return qs

    @action(detail=True, methods=['post'])
    def toggle_verify(self, request, pk=None):
        user = self.get_object()
        user.is_verified = not user.is_verified
        user.save(update_fields=['is_verified'])
        return Response({"id": user.id, "username": user.username, "is_verified": user.is_verified})
