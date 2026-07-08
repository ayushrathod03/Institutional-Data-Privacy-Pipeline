import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set style for professional presentation
sns.set_theme(style="whitegrid")
plt.rcParams.update({
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.titlesize': 16
})

def create_visualizations(processed_dir="data/processed", output_dir="plots"):
    csv_path = os.path.join(processed_dir, "df_sensors_clean.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Cleaned dataset not found at {csv_path}. Please run the cleaner pipeline first.")
        
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Reading cleaned dataset from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # 1. Plot: Electrical Load Scaling vs. Occupancy (Box/Violin Plot)
    plt.figure(figsize=(8, 6))
    # Order by size logically
    occupancy_order = ["1 (Single)", "2 (Coupled)", "5+ (Large)"]
    sns.boxplot(
        x="occupancy_group", 
        y="power_consumption", 
        data=df, 
        order=occupancy_order,
        palette="Blues"
    )
    plt.title("Electrical Load (Power) Distribution by Occupancy Group\n(One-Way ANOVA Verification)")
    plt.xlabel("Occupancy Group Category")
    plt.ylabel("Power Consumption (Watts)")
    plt.tight_layout()
    plot1_path = os.path.join(output_dir, "power_by_occupancy.png")
    plt.savefig(plot1_path, dpi=300)
    plt.close()
    print(f"Saved: {plot1_path}")
    
    # 2. Plot: Temperature Distribution by Motion Activity (Violin/Box Plot)
    plt.figure(figsize=(8, 6))
    motion_labels = {0: "Inactive (No Motion)", 1: "Active (Motion)"}
    df_temp_motion = df.copy()
    df_temp_motion["motion_label"] = df_temp_motion["motion_detector"].map(motion_labels)
    
    sns.violinplot(
        x="motion_label", 
        y="temperature", 
        data=df_temp_motion,
        palette="Oranges",
        inner="quartile"
    )
    plt.title("Indoor Temperature vs. Motion Activity\n(Independent Two-Sample t-Test Verification)")
    plt.xlabel("Activity Status")
    plt.ylabel("Indoor Temperature (°C)")
    plt.tight_layout()
    plot2_path = os.path.join(output_dir, "temp_by_motion.png")
    plt.savefig(plot2_path, dpi=300)
    plt.close()
    print(f"Saved: {plot2_path}")

    # 3. Plot: Diurnal Cycle Profile (Hourly Motion & Power Trends)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    
    hourly_stats = df.groupby(["hour", "occupancy_group"]).agg({
        "power_consumption": "mean",
        "motion_detector": "mean"
    }).reset_index()
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Left axis: Power
    sns.lineplot(
        x="hour", 
        y="power_consumption", 
        hue="occupancy_group", 
        hue_order=occupancy_order,
        data=hourly_stats, 
        ax=ax1,
        marker="o",
        linewidth=2
    )
    ax1.set_title("Hourly Behavioral & Load Profile over 24-Hour Cycle")
    ax1.set_xlabel("Hour of Day")
    ax1.set_ylabel("Average Power Consumption (Watts)")
    ax1.set_xticks(range(24))
    
    # Right axis: Motion Duty Cycle (shared)
    ax2 = ax1.twinx()
    # Aggregated motion profile overall
    overall_hourly_motion = df.groupby("hour")["motion_detector"].mean().reset_index()
    sns.lineplot(
        x="hour", 
        y="motion_detector", 
        data=overall_hourly_motion, 
        ax=ax2,
        color="purple",
        linestyle="--",
        linewidth=2,
        label="Overall Motion Prob.",
        legend=False
    )
    ax2.set_ylabel("Probability of Motion Activity (Purple Dashed)")
    ax2.grid(False)
    
    # Legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    # add secondary legend manually to first legend box
    purple_line = plt.Line2D([0], [0], color="purple", linestyle="--", linewidth=2)
    lines1.append(purple_line)
    labels1.append("Overall Motion Probability")
    ax1.legend(lines1, labels1, loc="upper left")
    
    plt.tight_layout()
    plot3_path = os.path.join(output_dir, "diurnal_hourly_profile.png")
    plt.savefig(plot3_path, dpi=300)
    plt.close()
    print(f"Saved: {plot3_path}")
    
    # 4. Plot: Pearson Correlation Heatmap
    # Re-calculate mapped numeric fields
    occupancy_mapping = {
        "1 (Single)": 1.0,
        "2 (Coupled)": 2.0,
        "3-4 (Family)": 3.5,
        "5+ (Large)": 5.5
    }
    df["occupancy_numeric"] = df["occupancy_group"].map(occupancy_mapping)
    corr_cols = ["temperature", "power_consumption", "motion_detector", "device_profile", "occupancy_numeric"]
    corr_matrix = df[corr_cols].corr(method="pearson")
    
    # Rename columns for presentation readability
    readable_cols = [
        "Temperature (°C)", 
        "Power Demand (W)", 
        "Motion (Active/Inactive)", 
        "Installed Smart Devices", 
        "Occupancy Size"
    ]
    corr_matrix.columns = readable_cols
    corr_matrix.index = readable_cols
    
    plt.figure(figsize=(8, 6))
    sns.heatmap(
        corr_matrix, 
        annot=True, 
        cmap="coolwarm", 
        vmin=-1, 
        vmax=1, 
        fmt=".3f", 
        linewidths=.5,
        square=True
    )
    plt.title("Feature Pearson Correlation Matrix\n(Relational Feature Co-Dependencies)")
    plt.tight_layout()
    plot4_path = os.path.join(output_dir, "correlation_heatmap.png")
    plt.savefig(plot4_path, dpi=300)
    plt.close()
    print(f"Saved: {plot4_path}")
    
    print("\nVisualizations generation completed successfully!")

if __name__ == "__main__":
    create_visualizations()
