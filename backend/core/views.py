import csv

from django.contrib.auth import authenticate
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ActivityRecord, AuditEvent, ImportBatch, Membership, SourceSystem
from .parsers import ingest_file
from .serializers import (
    ActivityRecordSerializer,
    AuditEventSerializer,
    ImportBatchSerializer,
    LoginSerializer,
    SignupSerializer,
    UserSerializer,
)
from .tenant import current_membership


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "token": result["token"],
                "user": UserSerializer(result["user"]).data,
                "organization": {"id": result["organization"].id, "name": result["organization"].name},
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        user = authenticate(username=email, password=serializer.validated_data["password"])
        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    membership = current_membership(request.user)
    qs = ActivityRecord.objects.filter(organization=membership.organization)
    batches = ImportBatch.objects.filter(organization=membership.organization)
    status_counts = {status_key: qs.filter(status=status_key).count() for status_key, _ in ActivityRecord.Status.choices}
    source_counts = {
        source_type: qs.filter(source__source_type=source_type).count() for source_type, _ in SourceSystem.SourceType.choices
    }
    scope_counts = {
        scope: qs.filter(scope_category=scope).count() for scope, _ in ActivityRecord.ScopeCategory.choices
    }
    return Response(
        {
            "status_counts": status_counts,
            "source_counts": source_counts,
            "scope_counts": scope_counts,
            "batch_counts": {
                "total": batches.count(),
                "received_rows": sum(b.received_count for b in batches),
                "failed_rows": sum(b.failed_count for b in batches),
                "suspicious_rows": sum(b.suspicious_count for b in batches),
            },
            "recent_batches": ImportBatchSerializer(batches[:6], many=True).data,
        }
    )


class ImportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ImportBatchSerializer

    def get_queryset(self):
        membership = current_membership(self.request.user)
        return ImportBatch.objects.filter(organization=membership.organization).select_related("source")

    @action(detail=False, methods=["post"])
    def upload(self, request):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot upload source data."}, status=status.HTTP_403_FORBIDDEN)
        source_type = request.data.get("source_type")
        upload = request.FILES.get("file")
        if source_type not in SourceSystem.SourceType.values:
            return Response({"detail": "Unsupported source_type."}, status=status.HTTP_400_BAD_REQUEST)
        if not upload:
            return Response({"detail": "file is required."}, status=status.HTTP_400_BAD_REQUEST)
        batch = ingest_file(membership.organization, request.user, source_type, upload.name, upload.read())
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ActivityRecordViewSet(viewsets.ModelViewSet):
    serializer_class = ActivityRecordSerializer

    def get_queryset(self):
        membership = current_membership(self.request.user)
        qs = (
            ActivityRecord.objects.filter(organization=membership.organization)
            .select_related("source", "raw_record", "import_batch")
            .prefetch_related("findings")
        )
        for param in ["status", "scope_category"]:
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source__source_type=source)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(findings__severity=severity).distinct()
        return qs

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Activity records are audit artifacts and cannot be deleted."}, status=405)

    def update(self, request, *args, **kwargs):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot edit activity records."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot edit activity records."}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot approve activity records."}, status=status.HTTP_403_FORBIDDEN)
        record = self.get_object()
        if record.findings.filter(severity="error").exists():
            return Response(
                {"detail": "Rows with error-level findings must be corrected or rejected before approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            record.approve(request.user, request.data.get("notes", ""))
            AuditEvent.objects.create(
                organization=record.organization,
                user=request.user,
                activity_record=record,
                event_type=AuditEvent.EventType.APPROVE,
                after={"status": record.status},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot reject activity records."}, status=status.HTTP_403_FORBIDDEN)
        record = self.get_object()
        try:
            record.reject(request.user, request.data.get("notes", ""))
            AuditEvent.objects.create(
                organization=record.organization,
                user=request.user,
                activity_record=record,
                event_type=AuditEvent.EventType.REJECT,
                after={"status": record.status},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot lock activity records."}, status=status.HTTP_403_FORBIDDEN)
        record = self.get_object()
        try:
            record.lock(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=False, methods=["post"])
    def bulk_approve(self, request):
        membership = current_membership(request.user)
        if membership.role == Membership.Role.AUDITOR:
            return Response({"detail": "Auditors cannot approve activity records."}, status=status.HTTP_403_FORBIDDEN)
        ids = request.data.get("ids", [])
        records = self.get_queryset().filter(id__in=ids).exclude(findings__severity="error")
        for record in records:
            if not record.is_locked and record.status != ActivityRecord.Status.APPROVED:
                record.approve(request.user, "Bulk approved clean row.")
        return Response({"approved_count": records.count()})


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        membership = current_membership(self.request.user)
        return AuditEvent.objects.filter(organization=membership.organization).select_related("user")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_locked(request):
    membership = current_membership(request.user)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="locked-audit-records.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "id",
            "source",
            "source_reference",
            "activity_type",
            "scope",
            "quantity",
            "unit",
            "period_start",
            "period_end",
            "location",
            "findings",
            "locked_at",
        ]
    )
    for record in (
        ActivityRecord.objects.filter(organization=membership.organization, status=ActivityRecord.Status.LOCKED)
        .select_related("source")
        .prefetch_related("findings")
    ):
        writer.writerow(
            [
                record.id,
                record.source.source_type,
                record.source_reference,
                record.activity_type,
                record.scope_category,
                record.normalized_quantity,
                record.normalized_unit,
                record.period_start,
                record.period_end,
                record.location_name or record.location_code,
                "; ".join(f"{f.severity}:{f.code}" for f in record.findings.all()),
                record.locked_at,
            ]
        )
    return response
