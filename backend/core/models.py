from django.conf import settings
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        ANALYST = "analyst", "Analyst"
        AUDITOR = "auditor", "Auditor"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ANALYST)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "organization")]


class SourceSystem(models.Model):
    class SourceType(models.TextChoices):
        SAP = "sap", "SAP fuel/procurement CSV"
        UTILITY = "utility", "Utility Green Button XML"
        TRAVEL = "travel", "Concur-style travel JSON"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="sources")
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    name = models.CharField(max_length=160)
    ingestion_mechanism = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "source_type")]


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="import_batches")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="import_batches")
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    received_count = models.PositiveIntegerField(default=0)
    normalized_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    suspicious_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class RawRecord(models.Model):
    class ParserStatus(models.TextChoices):
        NORMALIZED = "normalized", "Normalized"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="raw_records")
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="raw_records")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="raw_records")
    source_row_key = models.CharField(max_length=255, blank=True)
    row_number = models.PositiveIntegerField()
    payload = models.JSONField()
    parser_status = models.CharField(max_length=20, choices=ParserStatus.choices)
    parser_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "source_row_key"])]


class ActivityRecord(models.Model):
    class ScopeCategory(models.TextChoices):
        SCOPE_1 = "scope_1", "Scope 1"
        SCOPE_2 = "scope_2", "Scope 2"
        SCOPE_3 = "scope_3", "Scope 3"
        UNKNOWN = "unknown", "Unknown"

    class Status(models.TextChoices):
        PENDING = "pending_review", "Pending Review"
        SUSPICIOUS = "suspicious", "Suspicious"
        FAILED = "failed", "Failed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOCKED = "locked", "Locked"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="activity_records")
    source = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="activity_records")
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="activity_records")
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name="activity_record")
    source_row_key = models.CharField(max_length=255)
    activity_type = models.CharField(max_length=120)
    scope_category = models.CharField(max_length=20, choices=ScopeCategory.choices)
    original_quantity = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    original_unit = models.CharField(max_length=32, blank=True)
    normalized_quantity = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    normalized_unit = models.CharField(max_length=32, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    location_code = models.CharField(max_length=80, blank=True)
    location_name = models.CharField(max_length=160, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    confidence_score = models.PositiveSmallIntegerField(default=80)
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_records"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status", "scope_category"])]

    @property
    def is_locked(self):
        return self.status == self.Status.LOCKED or self.locked_at is not None

    def approve(self, user, notes=""):
        if self.is_locked:
            raise ValueError("Locked records cannot be approved again.")
        self.status = self.Status.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()
        Approval.objects.create(activity_record=self, user=user, decision=Approval.Decision.APPROVED, notes=notes)

    def reject(self, user, notes=""):
        if self.is_locked:
            raise ValueError("Locked records cannot be rejected.")
        self.status = self.Status.REJECTED
        self.save()
        Approval.objects.create(activity_record=self, user=user, decision=Approval.Decision.REJECTED, notes=notes)

    def lock(self, user):
        if self.status != self.Status.APPROVED:
            raise ValueError("Only approved records can be locked.")
        self.status = self.Status.LOCKED
        self.locked_at = timezone.now()
        self.save()
        AuditEvent.objects.create(
            organization=self.organization,
            user=user,
            activity_record=self,
            event_type=AuditEvent.EventType.LOCK,
            before={},
            after={"status": self.status, "locked_at": self.locked_at.isoformat()},
        )


class ReviewFinding(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    activity_record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="findings")
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Approval(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    activity_record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="approvals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    class EventType(models.TextChoices):
        IMPORT = "import", "Import"
        PARSE = "parse", "Parse"
        EDIT = "edit", "Edit"
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        LOCK = "lock", "Lock"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="audit_events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    activity_record = models.ForeignKey(
        ActivityRecord, null=True, blank=True, on_delete=models.CASCADE, related_name="audit_events"
    )
    import_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PlantLookup(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="plants")
    plant_code = models.CharField(max_length=40)
    plant_name = models.CharField(max_length=160)
    country = models.CharField(max_length=80)

    class Meta:
        unique_together = [("organization", "plant_code")]


class MeterLookup(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="meters")
    meter_id = models.CharField(max_length=80)
    facility_name = models.CharField(max_length=160)
    tariff = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = [("organization", "meter_id")]


class AirportLookup(models.Model):
    iata_code = models.CharField(max_length=3, unique=True)
    airport_name = models.CharField(max_length=160)
    city = models.CharField(max_length=120)
    country = models.CharField(max_length=80)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)


class UnitConversion(models.Model):
    source_unit = models.CharField(max_length=32)
    target_unit = models.CharField(max_length=32)
    multiplier = models.DecimalField(max_digits=16, decimal_places=8)
    activity_hint = models.CharField(max_length=80, blank=True)

    class Meta:
        unique_together = [("source_unit", "target_unit", "activity_hint")]


class EmissionFactor(models.Model):
    activity_type = models.CharField(max_length=120)
    scope_category = models.CharField(max_length=20, choices=ActivityRecord.ScopeCategory.choices)
    unit = models.CharField(max_length=32)
    factor = models.DecimalField(max_digits=14, decimal_places=6)
    source_note = models.CharField(max_length=255)
