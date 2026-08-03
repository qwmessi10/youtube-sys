from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import GlobalSettingViewSet, KeywordResultViewSet, KeywordRunViewSet, keyword_options

router = DefaultRouter()
router.register("settings", GlobalSettingViewSet, basename="settings")
router.register("keyword-runs", KeywordRunViewSet, basename="keyword-runs")
router.register("keyword-results", KeywordResultViewSet, basename="keyword-results")

urlpatterns = [path("keyword-options/", keyword_options), *router.urls]
