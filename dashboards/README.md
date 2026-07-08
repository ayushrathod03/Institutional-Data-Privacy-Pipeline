# Tableau Dashboard Integration Directory

This directory is configured to house the final `.twbx` (Tableau Packaged Workbook) file for the Smart Home Sensor Privacy & Compliance Analytics dashboard.

## Relational Data Source Setup

The cleaned, anonymized sensor dataset is structurally optimized to act as a flat, high-performance relational data source for Tableau:

* **Source File:** `data/processed/df_sensors_clean.csv`
* **Structure:** Denormalized flat file combining sensor logs and household descriptors.

### Data Model Mapping in Tableau

When connecting Tableau to `df_sensors_clean.csv`, apply the following configuration:

1. **Dimensions:**
   - `timestamp` -> Set as **Date & Time** type. Right-click to configure standard Date Hierarchies (Year, Quarter, Month, Day, Hour, Minute).
   - `household_id` -> Set as **String**. This is the 16-character SHA-256 salted hash representing de-identified homes.
   - `occupancy_group` -> Set as **String** (Nominal categorical dimension).
   - `motion_detector` -> Set as **Integer** (Binary flag: 1 = Motion, 0 = Inactive).

2. **Measures:**
   - `temperature` -> Set as **Decimal** (Celsius). Typically aggregated using `AVG`.
   - `power_consumption` -> Set as **Decimal** (Watts). Typically aggregated using `AVG` or `SUM` (to show total energy footprint).
   - `temperature_zscore` -> Set as **Decimal** (Normalized variance metric).
   - `power_zscore` -> Set as **Decimal** (Normalized variance metric).
   - `device_profile` -> Set as **Integer** (Count of smart devices per household).

### Suggested Visualizations
* **Behavioral Heatmaps:** Create an hourly heatmap displaying `motion_detector` rates or average `power_consumption` by hour of day (Y-axis) vs. `occupancy_group` (X-axis).
* **Sensor Variance Analysis:** Plot `temperature_zscore` and `power_zscore` over time to highlight peak fluctuations.
* **Correlation Scatters:** Plot `power_consumption` against `device_profile` colored by `occupancy_group` to visually highlight structural demand scaling.
