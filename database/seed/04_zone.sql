-- 04_zone.sql
-- Seed: the data zones, the same four as v2 (v2 had them only in its demo seed). Every install needs them:
-- the operational model builds the Silver zone and the dimensional model builds the Gold zone.
-- Safe to run again: MERGE adds new zones and updates names and descriptions.

MERGE INTO reference.zone AS t
USING (VALUES
    ('source', 'Source', 'Tables in the source systems.'),
    ('bronze', 'Bronze', 'Raw copies of the source tables in the data store.'),
    ('silver', 'Silver', 'Cleaned, conformed tables built from the operational model.'),
    ('gold',   'Gold',   'Reporting tables built from the dimensional model.')
) AS s (zone_code, zone_name, zone_description)
ON lower(btrim(t.zone_code)) = lower(btrim(s.zone_code))
WHEN MATCHED THEN UPDATE SET
    zone_name        = s.zone_name,
    zone_description = s.zone_description,
    updated_time     = CURRENT_TIMESTAMP,
    updated_by       = CURRENT_USER
WHEN NOT MATCHED THEN INSERT (zone_code, zone_name, zone_description)
    VALUES (s.zone_code, s.zone_name, s.zone_description);
