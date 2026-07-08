"""
Privacy & Governance Layer
===========================
This module enforces privacy constraints on sensitive datasets prior to exploratory data
analysis and analytical reporting, aligning with Institutional Review Board (IRB) 
ethical standards under the Common Rule (45 CFR 46) and HIPAA Safe Harbor protocols.

Core protection mechanisms:
1. PII Stripping: Direct identifiers (e.g., owner names, street addresses) are completely dropped.
2. Salted Cryptographic Hashing: Household identifiers are pseudonymized using SHA-256 with a salt.
3. Generalization: Occupancy numbers are collapsed into categorical bins to prevent re-identification via occupancy scale.
4. Differential Privacy: A Laplace mechanism is provided for numerical aggregates to guarantee epsilon-differential privacy.
"""

import hashlib
import numpy as np
import pandas as pd

DEFAULT_SALT = "SMARTHOME_SECURE_SALT_2026"

def deidentify_metadata(df_metadata, salt=DEFAULT_SALT):
    """
    Sanitizes household metadata to comply with HIPAA Safe Harbor and IRB guidelines.
    Strips direct PII (name, address), hashes the household_id, and generalizes occupancy size.
    
    Parameters:
    -----------
    df_metadata : pd.DataFrame
        Raw household metadata with columns: household_id, owner_name, street_address, occupancy_size, device_profile
    salt : str
        Salt for cryptographic hashing of household_id
        
    Returns:
    --------
    pd.DataFrame
        Anonymized metadata dataframe.
    """
    df = df_metadata.copy()
    
    # Verify presence of direct identifiers
    direct_pii = ["owner_name", "street_address"]
    for col in direct_pii:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)
            
    # Apply Salted Cryptographic Hashing to household_id
    if "household_id" in df.columns:
        df["household_id"] = df["household_id"].apply(
            lambda x: hashlib.sha256(f"{x}{salt}".encode("utf-8")).hexdigest()[:16]
        )
        
    # Generalize occupancy size into categorical bands to prevent attribute disclosure
    if "occupancy_size" in df.columns:
        def bin_occupancy(size):
            if size == 1:
                return "1 (Single)"
            elif size == 2:
                return "2 (Coupled)"
            elif 3 <= size <= 4:
                return "3-4 (Family)"
            else:
                return "5+ (Large)"
        df["occupancy_group"] = df["occupancy_size"].apply(bin_occupancy)
        df.drop(columns=["occupancy_size"], inplace=True)
        
    return df

def deidentify_sensor_logs(df_sensors, salt=DEFAULT_SALT):
    """
    De-identifies the household_id in sensor logs using the same salted hash function
    to maintain relational joining capabilities without exposing the raw ID.
    
    Parameters:
    -----------
    df_sensors : pd.DataFrame
        Raw sensor logs with household_id column.
    salt : str
        Cryptographic salt.
        
    Returns:
    --------
    pd.DataFrame
        De-identified sensor logs.
    """
    df = df_sensors.copy()
    if "household_id" in df.columns:
        df["household_id"] = df["household_id"].apply(
            lambda x: hashlib.sha256(f"{x}{salt}".encode("utf-8")).hexdigest()[:16] if pd.notna(x) else x
        )
    return df

class LaplaceDP:
    """
    Implements a local/global Laplace mechanism to apply Differential Privacy (DP)
    to query aggregates, ensuring mathematical privacy guarantees (epsilon).
    """
    @staticmethod
    def add_laplace_noise(val, sensitivity, epsilon):
        """
        Adds Laplace noise to a query value.
        Noise is drawn from Lap(0, scale) where scale = sensitivity / epsilon.
        
        Parameters:
        -----------
        val : float
            The aggregate value to sanitize.
        sensitivity : float
            The global sensitivity of the query (maximum impact of any single record).
        epsilon : float
            The privacy budget parameter. Lower epsilon means more privacy and more noise.
            
        Returns:
        --------
        float
            Sanitized value with added noise.
        """
        if epsilon <= 0:
            raise ValueError("Epsilon must be strictly positive (> 0)")
        scale = sensitivity / epsilon
        noise = np.random.laplace(0, scale)
        return val + noise

    @classmethod
    def private_mean(cls, series, val_range, epsilon):
        """
        Computes the differentially private mean of a numerical series.
        Uses the Laplace mechanism on both sum (sensitivity = range) and count (sensitivity = 1).
        
        Parameters:
        -----------
        series : pd.Series
            Numerical series.
        val_range : tuple (min_val, max_val)
            Expected domain limits for the series, defining query sensitivity.
        epsilon : float
            Privacy budget. Epsilon is split evenly between the sum and count queries (epsilon / 2 each).
        """
        series_clean = series.dropna()
        n = len(series_clean)
        if n == 0:
            return np.nan
            
        min_v, max_v = val_range
        actual_sum = series_clean.sum()
        
        # Clip values to range bounds to strictly enforce sensitivity
        clipped_series = series_clean.clip(min_v, max_v)
        clipped_sum = clipped_series.sum()
        
        # Sensitivity of sum is the maximum range height
        sensitivity_sum = max_v - min_v
        # Sensitivity of count is 1
        sensitivity_count = 1.0
        
        # Split epsilon budget
        eps_sum = epsilon * 0.5
        eps_count = epsilon * 0.5
        
        private_sum = cls.add_laplace_noise(clipped_sum, sensitivity_sum, eps_sum)
        private_count = cls.add_laplace_noise(n, sensitivity_count, eps_count)
        
        # Ensure count doesn't divide by zero or negative
        private_count = max(1.0, private_count)
        
        return private_sum / private_count
