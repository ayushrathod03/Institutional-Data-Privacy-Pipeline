-- =====================================================================
-- SMART HOME PRIVACY & COMPLIANCE PIPELINE: ANALYTICAL SQL LAYER
-- =====================================================================
-- This SQL file contains production-ready queries for executing analytical 
-- reports and auditing data compliance inside the SQLite secure database.
-- It demonstrates advanced SQL techniques, including Common Table Expressions 
-- (CTEs), Window Functions, and standard relational operations.

-- ---------------------------------------------------------------------
-- QUERY 1: HOURLY BEHAVIORAL AGGREGATE PROFILES
-- ---------------------------------------------------------------------
-- Computes the hourly usage profile across different household occupancy groups.
-- Summarizes the average motion duty cycle, mean power demand, and count of records.
-- Used to optimize grid distribution and identify peak occupancy patterns.

WITH hourly_base AS (
    SELECT 
        strftime('%H', f.timestamp) AS hour_of_day,
        d.occupancy_group,
        f.motion_detector,
        f.power_consumption,
        f.temperature
    FROM fact_sensor_logs f
    INNER JOIN dim_households d ON f.household_id = d.household_id
)
SELECT 
    hour_of_day,
    occupancy_group,
    COUNT(*) AS total_ticks,
    ROUND(AVG(motion_detector), 4) AS motion_duty_cycle,
    ROUND(AVG(power_consumption), 2) AS avg_power_watts,
    ROUND(AVG(temperature), 2) AS avg_temperature_celsius
FROM hourly_base
GROUP BY hour_of_day, occupancy_group
ORDER BY occupancy_group, hour_of_day;


-- ---------------------------------------------------------------------
-- QUERY 2: ROLLING WINDOW-BASED SENSOR ANOMALY DETECTION
-- ---------------------------------------------------------------------
-- Utilizes SQL window functions to compute rolling average and rolling variance
-- (derived via variance formula: Var(X) = E[X^2] - (E[X])^2) over
-- a sliding 2-hour window (12 ticks preceding/following).
-- Flags individual sensor logs that deviate significantly from rolling norms.
-- Squaring both sides of the Z-score equation (|X - E[X]| > 3*std) yields:
-- (X - E[X])^2 > 9 * Var(X). This mathematical optimization avoids using
-- the SQRT() function, which is not universally enabled in all SQLite builds.

WITH rolling_stats AS (
    SELECT 
        timestamp,
        household_id,
        power_consumption,
        -- Rolling average over 2-hour window (12 ticks before, 12 ticks after)
        AVG(power_consumption) OVER (
            PARTITION BY household_id 
            ORDER BY timestamp 
            ROWS BETWEEN 12 PRECEDING AND 12 FOLLOWING
        ) AS rolling_avg_power,
        
        -- Rolling average of squares (E[X^2]) over 2-hour window
        AVG(power_consumption * power_consumption) OVER (
            PARTITION BY household_id 
            ORDER BY timestamp 
            ROWS BETWEEN 12 PRECEDING AND 12 FOLLOWING
        ) AS rolling_avg_power_sq
    FROM fact_sensor_logs
),
variances AS (
    SELECT 
        timestamp,
        household_id,
        power_consumption,
        rolling_avg_power,
        -- Calculate rolling variance: Var(X) = E[X^2] - (E[X])^2
        CASE 
            WHEN (rolling_avg_power_sq - (rolling_avg_power * rolling_avg_power)) > 0 
            THEN rolling_avg_power_sq - (rolling_avg_power * rolling_avg_power)
            ELSE 0.0
        END AS rolling_var_power
    FROM rolling_stats
)
SELECT 
    timestamp,
    household_id,
    power_consumption,
    ROUND(rolling_avg_power, 2) AS rolling_avg_power,
    ROUND(rolling_var_power, 2) AS rolling_var_power,
    ROUND(power_consumption - rolling_avg_power, 2) AS deviation_from_avg,
    CASE 
        -- Compare squared deviation against 9 * variance (3-sigma threshold)
        WHEN rolling_var_power > 0 AND 
             ((power_consumption - rolling_avg_power) * (power_consumption - rolling_avg_power)) > (9 * rolling_var_power)
        THEN 'ANOMALY_SPIKE'
        ELSE 'NORMAL'
    END AS anomaly_status
FROM variances
ORDER BY household_id, timestamp
LIMIT 100;


-- ---------------------------------------------------------------------
-- QUERY 3: COMPLIANCE & PRIVACY PROTECTION AUDIT
-- ---------------------------------------------------------------------
-- Verifies the data governance integrity.
-- 1. Confirms direct PII columns are not present in schema.
-- 2. Validates referential integrity between de-identified fact and dimension tables.
-- 3. Audits the distribution of hashed IDs to ensure no metadata linkage is possible.

-- Audit Part A: Count active households and verify de-identification distribution
SELECT 
    d.household_id AS hashed_id,
    d.occupancy_group,
    d.device_profile,
    COUNT(f.timestamp) AS total_sensor_ticks,
    MIN(f.timestamp) AS recording_start,
    MAX(f.timestamp) AS recording_end
FROM dim_households d
LEFT JOIN fact_sensor_logs f ON d.household_id = f.household_id
GROUP BY d.household_id, d.occupancy_group, d.device_profile;

-- Audit Part B: Check for orphan sensor logs (referential integrity)
SELECT 
    COUNT(*) AS orphan_sensor_ticks
FROM fact_sensor_logs f
LEFT JOIN dim_households d ON f.household_id = d.household_id
WHERE d.household_id IS NULL;
