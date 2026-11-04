from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SMMAccountViewSet, SMMTaskViewSet

router = DefaultRouter()
router.register("smm-accounts", SMMAccountViewSet, basename="smm-accounts")
router.register("smm-tasks", SMMTaskViewSet, basename="smm-tasks")

urlpatterns = [*router.urls]
