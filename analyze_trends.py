import os
import json
import pandas as pd
import numpy as np
from scipy import stats

def run_statistical_analysis(processed_dir="data/processed"):
    csv_path = os.path.join(processed_dir, "df_sensors_clean.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Cleaned dataset not found at {csv_path}. Please run the cleaner script first.")
        
    print(f"Reading cleaned dataset from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # 1. Pearson Correlation Analysis
    # Let's map occupancy_group to numerical values for correlation purposes
    occupancy_mapping = {
        "1 (Single)": 1.0,
        "2 (Coupled)": 2.0,
        "3-4 (Family)": 3.5,
        "5+ (Large)": 5.5
    }
    df["occupancy_numeric"] = df["occupancy_group"].map(occupancy_mapping)
    
    corr_cols = ["temperature", "power_consumption", "motion_detector", "device_profile", "occupancy_numeric"]
    corr_matrix = df[corr_cols].corr(method="pearson")
    
    corr_path = os.path.join(processed_dir, "sensor_correlation_matrix.csv")
    corr_matrix.to_csv(corr_path)
    print(f"Saved Pearson correlation matrix to {corr_path}")
    
    # 2. Hypothesis Testing: One-Way ANOVA on Power Consumption across Occupancy Groups
    # Null Hypothesis (H0): Mean power consumption is identical across all occupancy groups.
    # Alternative Hypothesis (H1): At least one occupancy group exhibits a statistically different mean power consumption.
    groups = df["occupancy_group"].unique()
    power_groups = [df[df["occupancy_group"] == g]["power_consumption"].dropna().values for g in groups]
    
    f_stat, p_val_anova = stats.f_oneway(*power_groups)
    
    # Kruskal-Wallis Non-Parametric Test (as a robust check for non-normality)
    h_stat, p_val_kruskal = stats.kruskal(*power_groups)
    
    # Group-level descriptive statistics
    descriptives = {}
    for g in groups:
        sub_df = df[df["occupancy_group"] == g]["power_consumption"]
        descriptives[g] = {
            "mean_power_watts": round(float(sub_df.mean()), 2),
            "std_power_watts": round(float(sub_df.std()), 2),
            "median_power_watts": round(float(sub_df.median()), 2),
            "count": int(sub_df.count())
        }
        
    # 3. Two-Sample Independent T-Test: Temperature vs. Motion Activity
    # Null Hypothesis (H0): Mean indoor temperature is identical regardless of active movement.
    # Alternative Hypothesis (H1): Mean temperature is statistically different when motion is detected (active heat gains, HVAC adjustments).
    temp_motion_active = df[df["motion_detector"] == 1]["temperature"].dropna().values
    temp_motion_inactive = df[df["motion_detector"] == 0]["temperature"].dropna().values
    
    t_stat, p_val_ttest = stats.ttest_ind(temp_motion_active, temp_motion_inactive, equal_var=False)
    
    # Save all test results to a structured JSON file
    stats_summary = {
        "anova_test": {
            "f_statistic": round(float(f_stat), 4),
            "p_value": float(p_val_anova),
            "null_rejected": bool(p_val_anova < 0.05),
            "interpretation": "Mean power consumption differs significantly by occupancy group." if p_val_anova < 0.05 else "No statistically significant difference in mean power consumption by occupancy group."
        },
        "kruskal_wallis_test": {
            "h_statistic": round(float(h_stat), 4),
            "p_value": float(p_val_kruskal),
            "null_rejected": bool(p_val_kruskal < 0.05)
        },
        "t_test_temp_vs_motion": {
            "t_statistic": round(float(t_stat), 4),
            "p_value": float(p_val_ttest),
            "null_rejected": bool(p_val_ttest < 0.05),
            "mean_temp_motion_active": round(float(np.mean(temp_motion_active)), 2) if len(temp_motion_active) > 0 else 0.0,
            "mean_temp_motion_inactive": round(float(np.mean(temp_motion_inactive)), 2) if len(temp_motion_inactive) > 0 else 0.0,
            "interpretation": "Motion activity is associated with a statistically significant difference in temperature." if p_val_ttest < 0.05 else "No significant temperature difference associated with motion."
        },
        "descriptive_power_statistics": descriptives
    }
    
    summary_path = os.path.join(processed_dir, "statistical_analysis_results.json")
    with open(summary_path, "w") as f:
        json.dump(stats_summary, f, indent=4)
        
    print(f"Saved statistical analysis summary to {summary_path}")
    print(json.dumps(stats_summary, indent=2))
    
    return stats_summary

if __name__ == "__main__":
    run_statistical_analysis()
