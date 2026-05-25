from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .management.commands.seed_demo import Command
from .models import ActivityRecord, Membership, Organization, PlantLookup


class IngestionWorkflowTests(TestCase):
    def setUp(self):
        Command().handle()
        self.user = User.objects.get(username="analyst@acme.example")
        self.org = Organization.objects.get(slug="acme-manufacturing")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get(user=self.user).key}")

    def test_signup_creates_organization_membership(self):
        response = APIClient().post(
            "/api/auth/signup/",
            {
                "organization_name": "New Tenant",
                "email": "owner@example.com",
                "password": "StrongPass123!",
                "full_name": "Owner",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Membership.objects.filter(user__email="owner@example.com", organization__slug="new-tenant").exists())

    def test_sap_import_creates_raw_normalized_and_findings(self):
        payload = (
            "Belegnummer,Position,Werk,Material,Materialkurztext,Buchungsdatum,Menge,ME,Lieferant,Kategorie\n"
            "4900001,10,1000,DIESEL-01,Diesel fuel,2026-01-15,1200,L,VEND-1,Fuel\n"
            "4900002,10,ZZ99,LUBE-02,,15.01.2026,0,BBL,VEND-2,Procurement\n"
        )
        response = self.client.post(
            "/api/imports/upload/",
            {"source_type": "sap", "file": SimpleUploadedFile("sap.csv", payload.encode("utf-8"), content_type="text/csv")},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["failed_count"], 1)
        self.assertEqual(ActivityRecord.objects.filter(organization=self.org).count(), 2)
        self.assertTrue(ActivityRecord.objects.filter(status=ActivityRecord.Status.FAILED).exists())

    def test_tenant_isolation(self):
        other = Organization.objects.create(name="Other", slug="other")
        PlantLookup.objects.create(organization=other, plant_code="1000", plant_name="Other Plant", country="India")
        response = self.client.get("/api/activity-records/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_approve_lock_and_reject_edit_locked(self):
        self.test_sap_import_creates_raw_normalized_and_findings()
        record = ActivityRecord.objects.filter(organization=self.org, status=ActivityRecord.Status.PENDING).first()
        approve = self.client.post(f"/api/activity-records/{record.id}/approve/", {"notes": "Looks good"}, format="json")
        self.assertEqual(approve.status_code, 200)
        lock = self.client.post(f"/api/activity-records/{record.id}/lock/", {}, format="json")
        self.assertEqual(lock.status_code, 200)
        edit = self.client.patch(f"/api/activity-records/{record.id}/", {"location_name": "Changed"}, format="json")
        self.assertEqual(edit.status_code, 400)

    def test_utility_and_travel_imports(self):
        utility = """<greenButtonExport><reading id="u1"><meter_id>MTR-PUNE-001</meter_id><period_start>2026-01-01</period_start><period_end>2026-01-31</period_end><usage>45000</usage><unit>kWh</unit><tariff>HT Industrial TOU</tariff></reading></greenButtonExport>"""
        travel = """{"segments":[{"segment_id":"seg-1","trip_id":"t1","traveler":"Mira","category":"flight","origin_airport":"BOM","destination_airport":"DEL","start_date":"2026-01-18"},{"segment_id":"seg-2","trip_id":"t1","traveler":"Mira","category":"hotel","city":"Delhi","country":"India","nights":2,"start_date":"2026-01-18","end_date":"2026-01-20"}]}"""
        r1 = self.client.post(
            "/api/imports/upload/",
            {"source_type": "utility", "file": SimpleUploadedFile("utility.xml", utility.encode(), content_type="text/xml")},
        )
        r2 = self.client.post(
            "/api/imports/upload/",
            {"source_type": "travel", "file": SimpleUploadedFile("travel.json", travel.encode(), content_type="application/json")},
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(ActivityRecord.objects.filter(organization=self.org).count(), 3)
