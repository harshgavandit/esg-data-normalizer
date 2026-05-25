from django.contrib.auth.models import User
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from .models import (
    ActivityRecord,
    AuditEvent,
    ImportBatch,
    Membership,
    Organization,
    ReviewFinding,
    SourceSystem,
)


class SignupSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=180)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=10, write_only=True)
    full_name = serializers.CharField(max_length=180, required=False, allow_blank=True)

    def create(self, validated_data):
        email = validated_data["email"].lower()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=validated_data.get("full_name", ""),
        )
        base_slug = slugify(validated_data["organization_name"]) or "organization"
        slug = base_slug
        i = 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{i}"
            i += 1
        org = Organization.objects.create(name=validated_data["organization_name"], slug=slug)
        Membership.objects.create(user=user, organization=org, role=Membership.Role.ADMIN)
        for source_type, label in SourceSystem.SourceType.choices:
            SourceSystem.objects.create(
                organization=org,
                source_type=source_type,
                name=label,
                ingestion_mechanism={
                    "sap": "CSV upload",
                    "utility": "Green Button XML upload",
                    "travel": "Concur-style JSON upload",
                }[source_type],
                description="Realistic scoped ingestion mechanism for the prototype.",
            )
        token, _ = Token.objects.get_or_create(user=user)
        return {"token": token.key, "user": user, "organization": org}


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "role", "organization"]

    def get_role(self, obj):
        membership = obj.memberships.select_related("organization").first()
        return membership.role if membership else None

    def get_organization(self, obj):
        membership = obj.memberships.select_related("organization").first()
        if not membership:
            return None
        return {"id": membership.organization_id, "name": membership.organization.name, "slug": membership.organization.slug}


class ReviewFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewFinding
        fields = ["id", "code", "severity", "message", "created_at"]


class ActivityRecordSerializer(serializers.ModelSerializer):
    findings = ReviewFindingSerializer(many=True, read_only=True)
    raw_payload = serializers.SerializerMethodField()
    source_type = serializers.CharField(source="source.source_type", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = ActivityRecord
        fields = [
            "id",
            "source_type",
            "source_name",
            "source_row_key",
            "activity_type",
            "scope_category",
            "original_quantity",
            "original_unit",
            "normalized_quantity",
            "normalized_unit",
            "period_start",
            "period_end",
            "location_code",
            "location_name",
            "source_reference",
            "metadata",
            "status",
            "confidence_score",
            "approved_at",
            "locked_at",
            "created_at",
            "updated_at",
            "findings",
            "raw_payload",
        ]
        read_only_fields = ["status", "approved_at", "locked_at", "created_at", "updated_at"]

    def get_raw_payload(self, obj):
        return obj.raw_record.payload

    def update(self, instance, validated_data):
        if instance.is_locked:
            raise serializers.ValidationError("Locked records cannot be edited.")
        before = {
            "normalized_quantity": str(instance.normalized_quantity),
            "normalized_unit": instance.normalized_unit,
            "scope_category": instance.scope_category,
            "metadata": instance.metadata,
        }
        for field in [
            "activity_type",
            "scope_category",
            "normalized_quantity",
            "normalized_unit",
            "period_start",
            "period_end",
            "location_code",
            "location_name",
            "metadata",
        ]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.edited_by = self.context["request"].user
        instance.save()
        AuditEvent.objects.create(
            organization=instance.organization,
            user=self.context["request"].user,
            activity_record=instance,
            event_type=AuditEvent.EventType.EDIT,
            before=before,
            after={
                "normalized_quantity": str(instance.normalized_quantity),
                "normalized_unit": instance.normalized_unit,
                "scope_category": instance.scope_category,
                "metadata": instance.metadata,
            },
        )
        return instance


class ImportBatchSerializer(serializers.ModelSerializer):
    source_type = serializers.CharField(source="source.source_type", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "source_type",
            "source_name",
            "filename",
            "status",
            "received_count",
            "normalized_count",
            "failed_count",
            "suspicious_count",
            "started_at",
            "finished_at",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AuditEvent
        fields = ["id", "event_type", "user_email", "activity_record_id", "import_batch_id", "before", "after", "created_at"]
