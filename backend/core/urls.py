from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActivityRecordViewSet,
    AuditEventViewSet,
    ImportBatchViewSet,
    LoginView,
    SignupView,
    dashboard,
    export_locked,
    me,
)

router = DefaultRouter()
router.register("imports", ImportBatchViewSet, basename="imports")
router.register("activity-records", ActivityRecordViewSet, basename="activity-records")
router.register("audit-events", AuditEventViewSet, basename="audit-events")

urlpatterns = [
    path("auth/signup/", SignupView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/me/", me),
    path("dashboard/", dashboard),
    path("export/locked/", export_locked),
    path("", include(router.urls)),
]
