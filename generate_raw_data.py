import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_simulation_data(output_dir="data/raw", seed=42):
    np.random.seed(seed)
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Generate Household Metadata
    households = [
        {
            "household_id": "HH_001",
            "owner_name": "Alice Smith",
            "street_address": "123 Maple St, Springfield",
            "occupancy_size": 2,
            "device_profile": 12
        },
        {
            "household_id": "HH_002",
            "owner_name": "Bob Jones",
            "street_address": "456 Oak Ave, Springfield",
            "occupancy_size": 1,
            "device_profile": 8
        },
        {
            "household_id": "HH_003",
            "owner_name": "Charlie Brown",
            "street_address": "789 Pine Rd, Springfield",
            "occupancy_size": 5,
            "device_profile": 22
        }
    ]
    df_metadata = pd.DataFrame(households)
    metadata_path = os.path.join(output_dir, "household_metadata.csv")
    df_metadata.to_csv(metadata_path, index=False)
    print(f"Saved household metadata to {metadata_path}")
    
    # 2. Generate Noisy, Irregular Sensor Logs
    start_date = datetime(2026, 6, 1, 0, 0, 0)
    days = 14
    interval_minutes = 5
    ticks_per_day = 24 * 60 // interval_minutes
    total_ticks = days * ticks_per_day
    
    sensor_records = []
    
    # Define state transition probability matrices for Markov-chain motion simulation
    # Household states: active (1), sleep/away (0)
    for hh in households:
        hh_id = hh["household_id"]
        occ_size = hh["occupancy_size"]
        
        # Base parameters per household
        temp_base = 20.0 + (occ_size * 0.5)  # larger households run slightly warmer
        temp_amplitude = 2.0  # diurnal cycle temp amplitude
        power_base = 150.0 + (hh["device_profile"] * 10)  # always-on load
        
        current_time = start_date
        
        for tick in range(total_ticks):
            hour = current_time.hour
            
            # Determine probability of motion depending on hour
            if 0 <= hour < 6:      # Sleep hours
                prob_motion = 0.05
            elif 6 <= hour < 9:    # Morning routine
                prob_motion = 0.75
            elif 9 <= hour < 17:   # Work/School hours
                prob_motion = 0.20 if hh_id != "HH_001" else 0.60  # HH_001 works from home
            elif 17 <= hour < 22:  # Evening activity
                prob_motion = 0.85
            else:                  # Preparing for sleep
                prob_motion = 0.35
            
            motion = 1 if np.random.rand() < prob_motion else 0
            
            # Simulate Temperature: Diurnal cycle + Gaussian noise
            # Peaks around 3 PM (hour 15)
            diurnal_temp = temp_base + temp_amplitude * np.sin(np.pi * (hour - 9) / 12.0)
            noise_temp = np.random.normal(0, 0.4)
            temperature = round(diurnal_temp + noise_temp, 2)
            
            # Simulate Power Consumption: base load + usage due to occupancy and motion
            # When active/motion, power usage rises proportionally to occupancy
            noise_power = np.random.normal(0, 25.0)
            active_power = motion * occ_size * np.random.uniform(150, 350)
            power_consumption = round(max(0.0, power_base + active_power + noise_power), 1)
            
            sensor_records.append({
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "household_id": hh_id,
                "motion_detector": motion,
                "temperature": temperature,
                "power_consumption": power_consumption
            })
            
            current_time += timedelta(minutes=interval_minutes)
            
    df_sensors = pd.DataFrame(sensor_records)
    
    # 3. Inject Data Anomalies
    print("Injecting data quality anomalies...")
    raw_len = len(df_sensors)
    
    # A. Missing Timestamps (nullify timestamps in 3% of records)
    missing_ts_indices = np.random.choice(raw_len, size=int(raw_len * 0.03), replace=False)
    df_sensors.loc[missing_ts_indices, "timestamp"] = np.nan
    
    # B. Temperature Outlier Spikes (0.5% records)
    temp_spike_indices = np.random.choice(raw_len, size=int(raw_len * 0.005), replace=False)
    # inject extremely high or low temperatures
    for idx in temp_spike_indices:
        df_sensors.loc[idx, "temperature"] = np.random.choice([-99.0, 85.4, 120.0])
        
    # C. Power Consumption Outlier Spikes (0.5% records)
    power_spike_indices = np.random.choice(raw_len, size=int(raw_len * 0.005), replace=False)
    # inject massive power values
    for idx in power_spike_indices:
        df_sensors.loc[idx, "power_consumption"] = np.random.choice([750000.0, 999999.9])
        
    # D. Duplicate Records (2% records duplicated)
    dup_indices = np.random.choice(raw_len, size=int(raw_len * 0.02), replace=False)
    df_duplicates = df_sensors.iloc[dup_indices].copy()
    # perturb duplicate sensor values slightly or keep them identical
    df_duplicates["power_consumption"] = df_duplicates["power_consumption"] * np.random.choice([1.0, 1.05])
    df_sensors = pd.concat([df_sensors, df_duplicates], ignore_index=True)
    
    # Shuffle logs to simulate irregular streaming ingestion
    df_sensors = df_sensors.sample(frac=1, random_state=seed).reset_index(drop=True)
    
    sensors_path = os.path.join(output_dir, "sensor_logs.csv")
    df_sensors.to_csv(sensors_path, index=False)
    print(f"Saved noisy sensor logs to {sensors_path} (Total rows: {len(df_sensors)})")
    
if __name__ == "__main__":
    generate_simulation_data()
