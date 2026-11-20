from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import F, Q

from .models import Category, Crop, MandiPrice, CropStatus
from .serializers import (
    CategorySerializer,
    CropListSerializer,
    CropDetailSerializer,
    CropCreateUpdateSerializer,
    MandiPriceSerializer,
)
from .permissions import IsAdminOrReadOnly, IsFarmerOwnerOrReadOnly


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Produce Categories.
    - Public / Authenticated: Read categories.
    - Admin: Create, update, or deactivate categories.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        # If not staff/admin, only show active categories
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_admin_user):
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.crops.exists():
            return Response(
                {"detail": f"Cannot delete category '{instance.name}' because it contains {instance.crops.count()} active crop listings. Reassign or remove crops first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)


class CropViewSet(viewsets.ModelViewSet):
    """
    Comprehensive Crop Marketplace & Inventory API.
    - Public / Buyers: Browse available crops with rich search, filters, and sorting.
    - Farmers: Add crops, manage own listings, update stock and availability.
    """
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsFarmerOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['crop_name', 'variety', 'description', 'location_city', 'location_state']
    ordering_fields = ['price_per_unit', 'created_at', 'views_count', 'quantity_available']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CropCreateUpdateSerializer
        elif self.action == 'retrieve':
            return CropDetailSerializer
        return CropListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Crop.objects.select_related('farmer', 'category', 'farmer__user_profile', 'farmer__farmer_profile')

        # Object-level operations: allow object permission class (IsFarmerOwnerOrReadOnly)
        # to enforce ownership and return 403 Forbidden for unauthorized users
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy', 'toggle_availability']:
            return qs

        if self.action == 'my_crops':
            if user.is_authenticated:
                return qs.filter(farmer=user)
            return Crop.objects.none()

        # Public / Buyer Marketplace view: default to active listings with stock > 0
        show_all = self.request.query_params.get('show_all', 'false').lower() == 'true'
        if not (show_all and user.is_authenticated and getattr(user, 'is_admin_user', False)):
            qs = qs.filter(status=CropStatus.ACTIVE, quantity_available__gt=0)

        # Filter by Category (slug or ID)
        category_param = self.request.query_params.get('category')
        if category_param:
            if category_param.isdigit():
                qs = qs.filter(category_id=category_param)
            else:
                qs = qs.filter(category__slug=category_param)

        # Filter by Location (City or State)
        location = self.request.query_params.get('location')
        if location:
            qs = qs.filter(Q(location_city__icontains=location) | Q(location_state__icontains=location))

        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(location_city__iexact=city)

        state = self.request.query_params.get('state')
        if state:
            qs = qs.filter(location_state__iexact=state)

        # Filter by Price Range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            try:
                qs = qs.filter(price_per_unit__gte=float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                qs = qs.filter(price_per_unit__lte=float(max_price))
            except ValueError:
                pass

        # Filter by Quality Grade
        grade = self.request.query_params.get('grade')
        if grade:
            qs = qs.filter(grade_quality=grade)

        # Filter by Measurement Unit
        unit = self.request.query_params.get('unit')
        if unit:
            qs = qs.filter(unit=unit.lower())

        return qs

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        sort_by = self.request.query_params.get('sort_by')
        if sort_by == 'price_asc':
            return qs.order_by('price_per_unit')
        elif sort_by == 'price_desc':
            return qs.order_by('-price_per_unit')
        elif sort_by == 'popular':
            return qs.order_by('-views_count')
        elif sort_by == 'newest':
            return qs.order_by('-created_at')
        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment views atomically
        Crop.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_crops(self, request):
        """
        Endpoint for farmers to view all of their crop listings,
        including active, unavailable, and sold-out stock.
        """
        if not request.user.is_farmer and not request.user.is_admin_user:
            return Response(
                {"detail": "Only registered farmers can access their own crop inventory."},
                status=status.HTTP_403_FORBIDDEN
            )

        crops = Crop.objects.filter(farmer=request.user).select_related('category').order_by('-created_at')
        page = self.paginate_queryset(crops)
        if page is not None:
            serializer = CropListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = CropListSerializer(crops, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsFarmerOwnerOrReadOnly])
    def toggle_availability(self, request, pk=None):
        """Toggle a crop's status between 'active' and 'unavailable'."""
        crop = self.get_object()
        if crop.status == CropStatus.ACTIVE:
            crop.status = CropStatus.UNAVAILABLE
        else:
            crop.status = CropStatus.ACTIVE
        crop.save()
        return Response({
            "id": crop.id,
            "crop_name": crop.crop_name,
            "status": crop.status,
            "is_available": crop.is_available
        })


class MandiPriceViewSet(viewsets.ModelViewSet):
    """
    Regional APMC / Mandi market price benchmark data.
    Provides benchmark comparison data for buyers and farmers.
    - Public / Authenticated: Search and filter benchmark market rates.
    - Admin: Add or update price benchmarks.
    """
    queryset = MandiPrice.objects.all()
    serializer_class = MandiPriceSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['crop_name', 'market_name', 'district', 'state']
    ordering_fields = ['price_date', 'modal_price', 'crop_name']
    ordering = ['-price_date', 'crop_name']

    def get_queryset(self):
        qs = super().get_queryset()

        crop = self.request.query_params.get('crop')
        if crop:
            qs = qs.filter(crop_name__icontains=crop)

        state = self.request.query_params.get('state')
        if state:
            qs = qs.filter(state__iexact=state)

        market = self.request.query_params.get('market')
        if market:
            qs = qs.filter(market_name__icontains=market)

        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(price_date=date)

        return qs

    @action(detail=False, methods=['get'])
    def compare(self, request):
        """
        Compare a specific crop name across multiple mandis.
        Query param: ?crop=Wheat
        """
        crop_query = request.query_params.get('crop')
        if not crop_query:
            return Response(
                {"detail": "Please provide a 'crop' query parameter to compare (e.g. ?crop=Wheat)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        prices = MandiPrice.objects.filter(crop_name__icontains=crop_query).order_by('-price_date', 'modal_price')[:15]
        serializer = self.get_serializer(prices, many=True)
        return Response({
            "commodity": crop_query,
            "total_records": prices.count(),
            "benchmarks": serializer.data
        })
