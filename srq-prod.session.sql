SELECT version_num FROM alembic_version;

SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM activities;
SELECT COUNT(*) FROM activity_points;
SELECT COUNT(*) FROM activity_quality_metrics;
SELECT COUNT(*) FROM activity_quality_labels;

SELECT * FROM activity_quality_labels ORDER BY created_at DESC LIMIT 20;
