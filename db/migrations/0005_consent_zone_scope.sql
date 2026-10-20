-- Bind consented student groups to the zone data permitted in research exports.
CREATE TABLE IF NOT EXISTS student_profiles(student_id TEXT PRIMARY KEY, class_id TEXT NOT NULL, group_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS zone_group_access(zone_id TEXT NOT NULL REFERENCES zones(id), group_id TEXT NOT NULL, PRIMARY KEY(zone_id,group_id));
