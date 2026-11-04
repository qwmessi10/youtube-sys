from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SMMAccountViewSet, SMMPollTaskViewSet, SMMTaskViewSet

router = DefaultRouter()
router.register("smm-accounts", SMMAccountViewSet, basename="smm-accounts")
router.register("smm-tasks", SMMTaskViewSet, basename="smm-tasks")
router.register("smm-poll-tasks", SMMPollTaskViewSet, basename="smm-poll-tasks")

urlpatterns = [*router.urls]
