from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from rest_framework.authtoken.models import Token

from core.models import (
    AirportLookup,
    EmissionFactor,
    Membership,
    MeterLookup,
    Organization,
    PlantLookup,
    SourceSystem,
    UnitConversion,
)


class Command(BaseCommand):
    help = "Seed a reviewer-friendly demo organization, user, lookups, and factors."

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(name="Acme Manufacturing", slug=slugify("Acme Manufacturing"))
        user, created = User.objects.get_or_create(username="analyst@acme.example", defaults={"email": "analyst@acme.example"})
        user.email = "analyst@acme.example"
        user.first_name = "Demo Analyst"
        user.set_password("BreatheDemo123!")
        user.save()
        Token.objects.get_or_create(user=user)
        Membership.objects.get_or_create(user=user, organization=org, defaults={"role": Membership.Role.ADMIN})
        for source_type, label in SourceSystem.SourceType.choices:
            SourceSystem.objects.get_or_create(
                organization=org,
                source_type=source_type,
                defaults={
                    "name": label,
                    "ingestion_mechanism": {
                        "sap": "CSV upload",
                        "utility": "Green Button XML upload",
                        "travel": "Concur-style JSON upload",
                    }[source_type],
                    "description": "Seeded scoped source for assignment review.",
                },
            )
        for code, name, country in [
            ("1000", "Pune Assembly Plant", "India"),
            ("DE01", "Hamburg Components Plant", "Germany"),
        ]:
            PlantLookup.objects.get_or_create(organization=org, plant_code=code, defaults={"plant_name": name, "country": country})
        for meter_id, facility, tariff in [
            ("MTR-PUNE-001", "Pune Assembly Plant", "HT Industrial TOU"),
            ("MTR-HQ-009", "Mumbai Headquarters", "Commercial Green Rider"),
        ]:
            MeterLookup.objects.get_or_create(
                organization=org, meter_id=meter_id, defaults={"facility_name": facility, "tariff": tariff}
            )
        for code, name, city, country, lat, lon in [
            ("BOM", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "India", "19.0896", "72.8656"),
            ("DEL", "Indira Gandhi International Airport", "Delhi", "India", "28.5562", "77.1000"),
            ("SFO", "San Francisco International Airport", "San Francisco", "USA", "37.6213", "-122.3790"),
            ("FRA", "Frankfurt Airport", "Frankfurt", "Germany", "50.0379", "8.5622"),
        ]:
            AirportLookup.objects.get_or_create(
                iata_code=code,
                defaults={"airport_name": name, "city": city, "country": country, "latitude": lat, "longitude": lon},
            )
        for source_unit, target_unit, multiplier, hint in [
            ("GAL", "L", "3.78541", "sap"),
            ("MWH", "kWh", "1000", "electricity"),
            ("MI", "km", "1.60934", "travel"),
        ]:
            UnitConversion.objects.get_or_create(
                source_unit=source_unit,
                target_unit=target_unit,
                activity_hint=hint,
                defaults={"multiplier": Decimal(multiplier)},
            )
        for activity, scope, unit, factor, note in [
            ("Purchased electricity", "scope_2", "kWh", "0.716000", "India grid placeholder factor for prototype only"),
            ("Business flight", "scope_3", "km", "0.115000", "Illustrative passenger-km factor"),
            ("Hotel stay", "scope_3", "night", "18.000000", "Illustrative hotel-night factor"),
            ("SAP fuel/procurement", "scope_1", "L", "2.680000", "Illustrative diesel combustion factor"),
        ]:
            EmissionFactor.objects.get_or_create(
                activity_type=activity,
                scope_category=scope,
                unit=unit,
                defaults={"factor": Decimal(factor), "source_note": note},
            )
        self.stdout.write(self.style.SUCCESS("Seeded demo org analyst@acme.example / BreatheDemo123!"))
