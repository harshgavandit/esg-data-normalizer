import csv
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.db import transaction
from django.utils import timezone

from .models import (
    ActivityRecord,
    AirportLookup,
    AuditEvent,
    ImportBatch,
    MeterLookup,
    PlantLookup,
    RawRecord,
    ReviewFinding,
    SourceSystem,
    UnitConversion,
)


HEADER_ALIASES = {
    "Belegnummer": "document_number",
    "Materialbeleg": "document_number",
    "Document Number": "document_number",
    "Position": "line_item",
    "Plant": "plant_code",
    "Werk": "plant_code",
    "Material": "material_number",
    "Material Number": "material_number",
    "Materialkurztext": "material_description",
    "Material Description": "material_description",
    "Buchungsdatum": "posting_date",
    "Posting Date": "posting_date",
    "Menge": "quantity",
    "Quantity": "quantity",
    "ME": "unit",
    "Unit": "unit",
    "Vendor": "vendor",
    "Lieferant": "vendor",
    "Category": "category",
    "Kategorie": "category",
}


@dataclass
class Finding:
    code: str
    severity: str
    message: str


def normalize_unit(value, unit, activity_hint=""):
    if value is None or not unit:
        return None, "", [Finding("missing_unit", "error", "Quantity or unit is missing.")]
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None, unit, [Finding("bad_quantity", "error", "Quantity is not numeric.")]
    unit = unit.strip().upper()
    target = {
        "L": "L",
        "LTR": "L",
        "LITER": "L",
        "GAL": "L",
        "KWH": "kWh",
        "MWH": "kWh",
        "KG": "kg",
        "KM": "km",
        "MI": "km",
        "NIGHT": "night",
        "NIGHTS": "night",
    }.get(unit)
    if not target:
        return decimal_value, unit, [Finding("unknown_unit", "error", f"Unsupported unit '{unit}'.")]
    try:
        conversion = UnitConversion.objects.filter(source_unit=unit, target_unit=target).first()
        multiplier = Decimal(conversion.multiplier) if conversion else {
            ("GAL", "L"): Decimal("3.78541"),
            ("MWH", "kWh"): Decimal("1000"),
            ("MI", "km"): Decimal("1.60934"),
        }.get((unit, target), Decimal("1"))
        return decimal_value * multiplier, target, []
    except (InvalidOperation, TypeError):
        return None, target, [Finding("bad_quantity", "error", "Quantity is not numeric.")]


def parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def create_finding_records(activity, findings):
    for finding in findings:
        ReviewFinding.objects.create(
            activity_record=activity,
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
        )


def status_from_findings(findings):
    if any(f.severity == "error" for f in findings):
        return ActivityRecord.Status.FAILED
    if findings:
        return ActivityRecord.Status.SUSPICIOUS
    return ActivityRecord.Status.PENDING


def update_raw_parser_status(raw_record, findings):
    has_error = any(f.severity == "error" for f in findings)
    raw_record.parser_status = RawRecord.ParserStatus.FAILED if has_error else RawRecord.ParserStatus.NORMALIZED
    raw_record.parser_errors = [
        {"code": finding.code, "severity": finding.severity, "message": finding.message}
        for finding in findings
        if finding.severity == "error"
    ]
    raw_record.save(update_fields=["parser_status", "parser_errors"])


def confidence_from_findings(findings):
    score = 95
    for finding in findings:
        score -= 30 if finding.severity == "error" else 12
    return max(score, 20)


def duplicate_finding(org, source, key):
    if not key:
        return Finding("missing_source_row_key", "error", "Source row key is missing.")
    exists = RawRecord.objects.filter(organization=org, source=source, source_row_key=key).exists()
    if exists:
        return Finding("duplicate_source_row", "warning", "Duplicate source row key already exists for this source.")
    return None


@transaction.atomic
def ingest_file(organization, user, source_type, filename, file_bytes):
    source, _ = SourceSystem.objects.get_or_create(
        organization=organization,
        source_type=source_type,
        defaults={
            "name": SourceSystem.SourceType(source_type).label,
            "ingestion_mechanism": {
                "sap": "CSV upload",
                "utility": "Green Button XML upload",
                "travel": "Concur-style JSON upload",
            }[source_type],
            "description": "Scoped prototype source selected for realistic enterprise ESG ingestion.",
        },
    )
    batch = ImportBatch.objects.create(organization=organization, source=source, filename=filename)
    try:
        if source_type == SourceSystem.SourceType.SAP:
            records = parse_sap_csv(organization, source, batch, file_bytes.decode("utf-8-sig"))
        elif source_type == SourceSystem.SourceType.UTILITY:
            records = parse_utility_xml(organization, source, batch, file_bytes.decode("utf-8-sig"))
        elif source_type == SourceSystem.SourceType.TRAVEL:
            records = parse_travel_json(organization, source, batch, file_bytes.decode("utf-8-sig"))
        else:
            raise ValueError("Unsupported source type.")
        batch.received_count = RawRecord.objects.filter(import_batch=batch).count()
        batch.normalized_count = records
        batch.failed_count = RawRecord.objects.filter(import_batch=batch, parser_status=RawRecord.ParserStatus.FAILED).count()
        batch.suspicious_count = ActivityRecord.objects.filter(import_batch=batch, status=ActivityRecord.Status.SUSPICIOUS).count()
        batch.status = ImportBatch.Status.COMPLETE
    except Exception as exc:
        batch.status = ImportBatch.Status.FAILED
        AuditEvent.objects.create(
            organization=organization,
            user=user,
            import_batch=batch,
            event_type=AuditEvent.EventType.IMPORT,
            after={"error": str(exc)},
        )
        raise
    finally:
        batch.finished_at = timezone.now()
        batch.save()
    AuditEvent.objects.create(
        organization=organization,
        user=user,
        import_batch=batch,
        event_type=AuditEvent.EventType.IMPORT,
        after={"source_type": source_type, "filename": filename, "received_count": batch.received_count},
    )
    return batch


def parse_sap_csv(org, source, batch, text):
    rows = csv.DictReader(StringIO(text))
    count = 0
    for row_number, raw in enumerate(rows, start=2):
        row = {HEADER_ALIASES.get(k.strip(), k.strip()): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        key = f"{row.get('document_number','')}:{row.get('line_item','')}"
        findings = [f for f in [duplicate_finding(org, source, key)] if f]
        raw_record = RawRecord.objects.create(
            organization=org,
            import_batch=batch,
            source=source,
            source_row_key=key,
            row_number=row_number,
            payload=row,
            parser_status=RawRecord.ParserStatus.NORMALIZED,
        )
        quantity = row.get("quantity")
        normalized_quantity, normalized_unit, unit_findings = normalize_unit(quantity, row.get("unit"), "sap")
        findings.extend(unit_findings)
        posting_date = parse_date(row.get("posting_date"))
        if not posting_date:
            findings.append(Finding("bad_date", "error", "Posting date could not be parsed."))
        if normalized_quantity is not None and normalized_quantity <= 0:
            findings.append(Finding("non_positive_quantity", "error", "Quantity is zero or negative."))
        plant = PlantLookup.objects.filter(organization=org, plant_code=row.get("plant_code", "")).first()
        if not plant:
            findings.append(Finding("unknown_plant", "warning", "Plant code is not in the lookup table."))
        if not row.get("material_description"):
            findings.append(Finding("missing_material_description", "warning", "Material description is missing."))
        category = (row.get("category") or row.get("material_description") or "").lower()
        scope = ActivityRecord.ScopeCategory.SCOPE_1 if any(w in category for w in ["diesel", "fuel", "natural gas"]) else ActivityRecord.ScopeCategory.SCOPE_3
        activity = ActivityRecord.objects.create(
            organization=org,
            source=source,
            import_batch=batch,
            raw_record=raw_record,
            source_row_key=key,
            activity_type="SAP fuel/procurement",
            scope_category=scope,
            original_quantity=Decimal(quantity) if quantity else None,
            original_unit=row.get("unit", ""),
            normalized_quantity=normalized_quantity,
            normalized_unit=normalized_unit,
            period_start=posting_date,
            period_end=posting_date,
            location_code=row.get("plant_code", ""),
            location_name=plant.plant_name if plant else "",
            source_reference=row.get("document_number", ""),
            metadata={"material_number": row.get("material_number"), "vendor": row.get("vendor"), "category": row.get("category")},
            status=status_from_findings(findings),
            confidence_score=confidence_from_findings(findings),
        )
        create_finding_records(activity, findings)
        update_raw_parser_status(raw_record, findings)
        count += 1
    return count


def parse_utility_xml(org, source, batch, text):
    root = ET.fromstring(text)
    readings = root.findall(".//reading")
    count = 0
    for row_number, reading in enumerate(readings, start=1):
        payload = dict(reading.attrib)
        payload.update({child.tag: child.text for child in reading})
        key = payload.get("id") or f"{payload.get('meter_id','')}:{payload.get('period_start','')}"
        findings = [f for f in [duplicate_finding(org, source, key)] if f]
        raw_record = RawRecord.objects.create(
            organization=org,
            import_batch=batch,
            source=source,
            source_row_key=key,
            row_number=row_number,
            payload=payload,
            parser_status=RawRecord.ParserStatus.NORMALIZED,
        )
        meter = MeterLookup.objects.filter(organization=org, meter_id=payload.get("meter_id", "")).first()
        if not meter:
            findings.append(Finding("unknown_meter", "warning", "Meter ID is not in the lookup table."))
        quantity, unit, unit_findings = normalize_unit(payload.get("usage"), payload.get("unit") or "kWh", "electricity")
        findings.extend(unit_findings)
        start = parse_date(payload.get("period_start"))
        end = parse_date(payload.get("period_end"))
        if not start or not end:
            findings.append(Finding("bad_date", "error", "Billing period dates could not be parsed."))
        elif (end - start).days < 20 or (end - start).days > 45:
            findings.append(Finding("odd_billing_period", "warning", "Billing period does not look like a normal monthly cycle."))
        if quantity is not None and quantity <= 0:
            findings.append(Finding("non_positive_quantity", "error", "Electricity usage is zero or negative."))
        activity = ActivityRecord.objects.create(
            organization=org,
            source=source,
            import_batch=batch,
            raw_record=raw_record,
            source_row_key=key,
            activity_type="Purchased electricity",
            scope_category=ActivityRecord.ScopeCategory.SCOPE_2,
            original_quantity=Decimal(payload.get("usage")) if payload.get("usage") else None,
            original_unit=payload.get("unit", "kWh"),
            normalized_quantity=quantity,
            normalized_unit=unit,
            period_start=start,
            period_end=end,
            location_code=payload.get("meter_id", ""),
            location_name=meter.facility_name if meter else "",
            source_reference=key,
            metadata={"tariff": payload.get("tariff"), "service_address": payload.get("service_address")},
            status=status_from_findings(findings),
            confidence_score=confidence_from_findings(findings),
        )
        create_finding_records(activity, findings)
        update_raw_parser_status(raw_record, findings)
        count += 1
    return count


def parse_travel_json(org, source, batch, text):
    data = json.loads(text)
    segments = data.get("segments", [])
    count = 0
    for row_number, segment in enumerate(segments, start=1):
        key = segment.get("segment_id", "")
        findings = [f for f in [duplicate_finding(org, source, key)] if f]
        raw_record = RawRecord.objects.create(
            organization=org,
            import_batch=batch,
            source=source,
            source_row_key=key,
            row_number=row_number,
            payload=segment,
            parser_status=RawRecord.ParserStatus.NORMALIZED,
        )
        category = segment.get("category")
        start = parse_date(segment.get("start_date"))
        end = parse_date(segment.get("end_date")) or start
        quantity = None
        unit = ""
        activity_type = ""
        metadata = {"traveler": segment.get("traveler"), "trip_id": segment.get("trip_id")}
        location_code = ""
        if category == "flight":
            activity_type = "Business flight"
            origin = segment.get("origin_airport")
            destination = segment.get("destination_airport")
            location_code = f"{origin}-{destination}"
            distance = segment.get("distance_km")
            if not distance:
                distance = airport_distance_km(origin, destination)
                if not distance:
                    findings.append(Finding("missing_flight_distance", "error", "Flight distance is missing and airport lookup failed."))
            quantity = distance
            unit = "km"
            metadata.update({"origin_airport": origin, "destination_airport": destination, "cabin": segment.get("cabin")})
        elif category == "hotel":
            activity_type = "Hotel stay"
            quantity = segment.get("nights")
            unit = "night"
            location_code = segment.get("city", "")
            if not quantity:
                findings.append(Finding("missing_hotel_nights", "error", "Hotel nights are missing."))
            metadata.update({"city": segment.get("city"), "country": segment.get("country")})
        elif category == "ground":
            activity_type = "Ground transport"
            quantity = segment.get("distance_km")
            unit = "km"
            location_code = segment.get("city", "")
            if not quantity:
                findings.append(Finding("missing_ground_distance", "warning", "Ground transport distance is missing."))
            metadata.update({"mode": segment.get("mode"), "city": segment.get("city")})
        else:
            activity_type = "Unsupported travel category"
            findings.append(Finding("unsupported_travel_category", "error", "Travel category cannot be mapped."))
        normalized_quantity, normalized_unit, unit_findings = normalize_unit(quantity, unit, "travel")
        findings.extend(unit_findings)
        if not start:
            findings.append(Finding("bad_date", "error", "Travel segment date could not be parsed."))
        if normalized_quantity is not None and normalized_quantity <= 0:
            findings.append(Finding("non_positive_quantity", "error", "Travel quantity is zero or negative."))
        activity = ActivityRecord.objects.create(
            organization=org,
            source=source,
            import_batch=batch,
            raw_record=raw_record,
            source_row_key=key,
            activity_type=activity_type,
            scope_category=ActivityRecord.ScopeCategory.SCOPE_3,
            original_quantity=Decimal(str(quantity)) if quantity else None,
            original_unit=unit,
            normalized_quantity=normalized_quantity,
            normalized_unit=normalized_unit,
            period_start=start,
            period_end=end,
            location_code=location_code,
            location_name=segment.get("city", ""),
            source_reference=key,
            metadata=metadata,
            status=status_from_findings(findings),
            confidence_score=confidence_from_findings(findings),
        )
        create_finding_records(activity, findings)
        update_raw_parser_status(raw_record, findings)
        count += 1
    return count


def airport_distance_km(origin, destination):
    if not origin or not destination:
        return None
    a = AirportLookup.objects.filter(iata_code=origin.upper()).first()
    b = AirportLookup.objects.filter(iata_code=destination.upper()).first()
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, [float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return Decimal(str(round(6371 * 2 * math.asin(math.sqrt(h)), 2)))
