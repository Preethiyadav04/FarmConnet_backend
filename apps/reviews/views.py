from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404

from .models import Review, Favorite
from .serializers import ReviewSerializer, FavoriteSerializer
from .permissions import IsReviewAuthorOrReadOnly
from apps.accounts.models import UserRole
from django.contrib.auth import get_user_model

User = get_user_model()


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Farmer Reviews & Ratings ViewSet.
    - Buyers can submit reviews only for completed/delivered orders.
    - Duplicate reviews for the same order are strictly blocked.
    - Public / authenticated users can view ratings and written testimonials.
    - Modification and deletion restricted strictly to the review author or admin.
    """
    queryset = Review.objects.select_related('buyer', 'farmer', 'crop_listing', 'order').all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsReviewAuthorOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        farmer_id = self.request.query_params.get('farmer_id')
        crop_id = self.request.query_params.get('crop_id')
        rating = self.request.query_params.get('rating')

        if farmer_id:
            qs = qs.filter(farmer_id=farmer_id)
        if crop_id:
            qs = qs.filter(crop_listing_id=crop_id)
        if rating:
            qs = qs.filter(rating=rating)

        return qs

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def farmer_summary(self, request):
        """Returns aggregated rating score, review count, and star distribution for a farmer."""
        farmer_id = request.query_params.get('farmer_id')
        if not farmer_id:
            if request.user.is_authenticated and getattr(request.user, 'is_farmer', False):
                farmer_id = request.user.id
            else:
                return Response({"detail": "Please provide 'farmer_id' query parameter."}, status=status.HTTP_400_BAD_REQUEST)

        farmer = get_object_or_404(User, id=farmer_id, role=UserRole.FARMER)
        reviews = Review.objects.filter(farmer=farmer)
        stats = reviews.aggregate(avg_rating=Avg('rating'), count=Count('id'))

        # Star breakdown (1 to 5)
        breakdown = {i: 0 for i in range(1, 6)}
        for item in reviews.values('rating').annotate(c=Count('id')):
            breakdown[item['rating']] = item['c']

        avg_val = round(stats['avg_rating'], 2) if stats['avg_rating'] else 0.0

        return Response({
            "farmer_id": farmer.id,
            "farmer_username": farmer.username,
            "average_rating": avg_val,
            "total_reviews": stats['count'] or 0,
            "breakdown": breakdown
        })


class FavoriteViewSet(viewsets.ModelViewSet):
    """
    Buyer favorite crops management.
    """
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Favorite.objects.filter(buyer=self.request.user).select_related('crop_listing', 'crop_listing__farmer')

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """Toggle bookmark on a crop listing: adds if not favorited, removes if already favorited."""
        crop_id = request.data.get('crop_id')
        if not crop_id:
            return Response({"detail": "Please provide 'crop_id'."}, status=status.HTTP_400_BAD_REQUEST)

        fav = Favorite.objects.filter(buyer=request.user, crop_listing_id=crop_id).first()
        if fav:
            fav.delete()
            return Response({"crop_id": crop_id, "is_favorited": False, "message": "Crop removed from favorites."})
        else:
            Favorite.objects.create(buyer=request.user, crop_listing_id=crop_id)
            return Response({"crop_id": crop_id, "is_favorited": True, "message": "Crop saved to favorites."}, status=status.HTTP_201_CREATED)
