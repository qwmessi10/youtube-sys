from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CompetitorAnalysisViewSet,
    KeywordRankTrackingViewSet,
    VideoLibraryItemViewSet,
    dashboard_summary,
)

router = DefaultRouter()
router.register("analytics-videos", VideoLibraryItemViewSet, basename="analytics-videos")
router.register("analytics-competitor", CompetitorAnalysisViewSet, basename="analytics-competitor")
router.register("analytics-rank-trackings", KeywordRankTrackingViewSet, basename="analytics-rank-trackings")

urlpatterns = [path("dashboard/summary/", dashboard_summary), *router.urls]
