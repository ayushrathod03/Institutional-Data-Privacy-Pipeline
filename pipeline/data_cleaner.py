import os
import sqlite3
import json
import pandas as pd
import numpy as np
from pipeline.privacy_governance import deidentify_metadata, deidentify_sensor_logs

def clean_and_store_data(raw_dir="data/raw", processed_dir="data/processed"):
    os.makedirs(processed_dir, exist_ok=True)
    
    # Paths
    raw_sensors_path = os.path.join(raw_dir, "sensor_logs.csv")
    raw_meta_path = os.path.join(raw_dir, "household_metadata.csv")
    db_path = os.path.join(processed_dir, "secure_analytics.db")
    
    print(f"Reading raw datasets from {raw_dir}...")
    df_raw_sensors = pd.read_csv(raw_sensors_path)
    df_raw_meta = pd.read_csv(raw_meta_path)
    
    provenance_log = {
        "raw_sensor_records": len(df_raw_sensors),
        "raw_metadata_records": len(df_raw_meta)
    }
    
    # --- 1. Deduplication ---
    # Identify exact duplicates or duplicate ticks (matching household_id and timestamp)
    # We drop completely null timestamps first to avoid duplication issues
    df_clean_sensors = df_raw_sensors.dropna(subset=["timestamp"]).copy()
    provenance_log["missing_timestamps_dropped"] = len(df_raw_sensors) - len(df_clean_sensors)
    
    # Sort by timestamp
    df_clean_sensors = df_clean_sensors.sort_values(by=["household_id", "timestamp"])
    
    # Identify duplicate ticks
    duplicated_mask = df_clean_sensors.duplicated(subset=["household_id", "timestamp"], keep="first")
    provenance_log["duplicate_records_removed"] = int(duplicated_mask.sum())
    
    df_clean_sensors = df_clean_sensors[~duplicated_mask].copy()
    
    # --- 2. Alignment & Resampling (Grid Reindexing) ---
    df_clean_sensors["timestamp"] = pd.to_datetime(df_clean_sensors["timestamp"])
    
    # Group by household and resample to a strict 5-minute interval
    resampled_dfs = []
    for hh_id, group in df_clean_sensors.groupby("household_id"):
        group = group.set_index("timestamp")
        # Find the min and max timestamp boundaries for this household
        min_time = group.index.min()
        max_time = group.index.max()
        # Create full 5-minute index range
        full_index = pd.date_range(start=min_time, end=max_time, freq="5min")
        # Reindex to insert NaNs for any missing gaps
        resampled_group = group.reindex(full_index)
        resampled_group["household_id"] = hh_id
        resampled_group = resampled_group.reset_index().rename(columns={"index": "timestamp"})
        resampled_dfs.append(resampled_group)
        
    df_clean_sensors = pd.concat(resampled_dfs, ignore_index=True)
    provenance_log["grid_aligned_records"] = len(df_clean_sensors)
    
    # --- 3. Outlier / Spike Detection and Clamping ---
    # Standard home ranges: Temperature 10°C to 45°C, Power 0W to 15,000W
    temp_min, temp_max = 10.0, 45.0
    power_min, power_max = 0.0, 15000.0
    
    temp_outliers = (df_clean_sensors["temperature"] < temp_min) | (df_clean_sensors["temperature"] > temp_max)
    power_outliers = (df_clean_sensors["power_consumption"] < power_min) | (df_clean_sensors["power_consumption"] > power_max)
    
    provenance_log["temperature_outliers_clamped"] = int(temp_outliers.sum())
    provenance_log["power_outliers_clamped"] = int(power_outliers.sum())
    
    # Set outliers to NaN so they can be imputed along with missing values
    df_clean_sensors.loc[temp_outliers, "temperature"] = np.nan
    df_clean_sensors.loc[power_outliers, "power_consumption"] = np.nan
    
    # --- 4. Statistical Imputation ---
    # Record missing counts before imputation
    provenance_log["missing_temperature_before_imputation"] = int(df_clean_sensors["temperature"].isna().sum())
    provenance_log["missing_power_before_imputation"] = int(df_clean_sensors["power_consumption"].isna().sum())
    
    # A. Linear interpolation for short temperature gaps (limit = 3 ticks / 15 mins)
    df_clean_sensors["temperature"] = df_clean_sensors.groupby("household_id")["temperature"].transform(
        lambda x: x.interpolate(method="linear", limit=3)
    )
    
    # B. For remaining NaNs (large temperature gaps and all power consumption NaNs),
    # impute with the household-specific median for that hour of the day.
    df_clean_sensors["hour"] = df_clean_sensors["timestamp"].dt.hour
    
    # Calculate medians by household and hour
    temp_medians = df_clean_sensors.groupby(["household_id", "hour"])["temperature"].transform("median")
    power_medians = df_clean_sensors.groupby(["household_id", "hour"])["power_consumption"].transform("median")
    
    # Fill values
    df_clean_sensors["temperature"] = df_clean_sensors["temperature"].fillna(temp_medians)
    df_clean_sensors["power_consumption"] = df_clean_sensors["power_consumption"].fillna(power_medians)
    
    # If any NaNs remain (e.g. household has NO data for that hour), fall back to global mean
    df_clean_sensors["temperature"] = df_clean_sensors["temperature"].fillna(df_clean_sensors["temperature"].mean())
    df_clean_sensors["power_consumption"] = df_clean_sensors["power_consumption"].fillna(df_clean_sensors["power_consumption"].mean())
    
    # C. Impute motion_detector (binary): forward fill, then fill remaining with 0 (default inactive)
    df_clean_sensors["motion_detector"] = df_clean_sensors.groupby("household_id")["motion_detector"].transform(
        lambda x: x.ffill().fillna(0).astype(int)
    )
    
    # --- 5. Variance Normalization ---
    # Standard scale (Z-score) temperature and power consumption per household
    df_clean_sensors["temperature_zscore"] = df_clean_sensors.groupby("household_id")["temperature"].transform(
        lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0.0
    )
    df_clean_sensors["power_zscore"] = df_clean_sensors.groupby("household_id")["power_consumption"].transform(
        lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0.0
    )
    
    # Round metrics to keep data clean
    df_clean_sensors["temperature"] = df_clean_sensors["temperature"].round(2)
    df_clean_sensors["power_consumption"] = df_clean_sensors["power_consumption"].round(1)
    df_clean_sensors["temperature_zscore"] = df_clean_sensors["temperature_zscore"].round(4)
    df_clean_sensors["power_zscore"] = df_clean_sensors["power_zscore"].round(4)
    
    # Drop intermediate columns
    df_clean_sensors = df_clean_sensors.drop(columns=["hour"])
    
    # --- 6. Privacy & Governance Layer Application ---
    print("Applying privacy governance policies (PII stripping, salted hashing, generalization)...")
    # De-identify metadata
    df_meta_clean = deidentify_metadata(df_raw_meta)
    
    # De-identify sensor logs
    df_sensors_clean = deidentify_sensor_logs(df_clean_sensors)
    
    # --- 7. SQLite Storage ---
    print(f"Writing cleaned, anonymized datasets to SQLite database: {db_path}...")
    conn = sqlite3.connect(db_path)
    
    # Convert timestamps back to string format for simple SQLite storage
    df_sensors_sql = df_sensors_clean.copy()
    df_sensors_sql["timestamp"] = df_sensors_sql["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    
    df_meta_clean.to_sql("dim_households", conn, if_exists="replace", index=False)
    df_sensors_sql.to_sql("fact_sensor_logs", conn, if_exists="replace", index=False)
    conn.close()
    
    # --- 8. Tableau-Optimized Exports ---
    # Merge datasets to create a flat table optimized for Tableau
    df_tableau = df_sensors_clean.merge(df_meta_clean, on="household_id", how="left")
    
    # Format timestamp as string for CSV export
    df_tableau["timestamp"] = df_tableau["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    
    tableau_csv_path = os.path.join(processed_dir, "df_sensors_clean.csv")
    df_tableau.to_csv(tableau_csv_path, index=False)
    print(f"Saved Tableau-optimized flat dataset to {tableau_csv_path}")
    
    meta_csv_path = os.path.join(processed_dir, "df_households_clean.csv")
    df_meta_clean.to_csv(meta_csv_path, index=False)
    
    # Save Provenance Logs
    provenance_path = os.path.join(processed_dir, "provenance_summary.json")
    with open(provenance_path, "w") as f:
        json.dump(provenance_log, f, indent=4)
    print(f"Saved dataset provenance logs to {provenance_path}")
    print(json.dumps(provenance_log, indent=2))
    
    return df_tableau

if __name__ == "__main__":
    clean_and_store_data()
