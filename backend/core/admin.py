from django.contrib import admin

from . import models

for model in [
    models.Organization,
    models.Membership,
    models.SourceSystem,
    models.ImportBatch,
    models.RawRecord,
    models.ActivityRecord,
    models.ReviewFinding,
    models.Approval,
    models.AuditEvent,
    models.PlantLookup,
    models.MeterLookup,
    models.AirportLookup,
    models.UnitConversion,
    models.EmissionFactor,
]:
    admin.site.register(model)

