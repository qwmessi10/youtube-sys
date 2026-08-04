from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AgentPromptViewSet, GlobalSettingViewSet, KeywordResultViewSet, KeywordRunViewSet, keyword_options

router = DefaultRouter()
router.register("settings", GlobalSettingViewSet, basename="settings")
router.register("keyword-runs", KeywordRunViewSet, basename="keyword-runs")
router.register("keyword-results", KeywordResultViewSet, basename="keyword-results")
router.register("agent-prompts", AgentPromptViewSet, basename="agent-prompts")

urlpatterns = [path("keyword-options/", keyword_options), *router.urls]
