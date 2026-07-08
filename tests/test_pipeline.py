import os
import sqlite3
import unittest
import numpy as np
import pandas as pd
from pipeline.privacy_governance import deidentify_metadata, deidentify_sensor_logs, LaplaceDP
from pipeline.data_cleaner import clean_and_store_data

class TestCompliancePipeline(unittest.TestCase):
    def setUp(self):
        # Paths to project deliverables
        self.db_path = "data/processed/secure_analytics.db"
        self.processed_csv = "data/processed/df_sensors_clean.csv"
        
        # Create a mock metadata dataset for isolation testing
        self.mock_metadata = pd.DataFrame([
            {
                "household_id": "HH_TEST_01",
                "owner_name": "John Doe",
                "street_address": "999 Testing Dr",
                "occupancy_size": 1,
                "device_profile": 5
            },
            {
                "household_id": "HH_TEST_02",
                "owner_name": "Jane Doe",
                "street_address": "888 Debugging Ln",
                "occupancy_size": 4,
                "device_profile": 15
            }
        ])

    def test_pii_leakage_prevention(self):
        """
        Verify that direct identifiers (names, addresses) are completely dropped 
        by the de-identification function.
        """
        df_anonymized = deidentify_metadata(self.mock_metadata)
        
        self.assertNotIn("owner_name", df_anonymized.columns)
        self.assertNotIn("street_address", df_anonymized.columns)
        self.assertIn("household_id", df_anonymized.columns)
        self.assertIn("occupancy_group", df_anonymized.columns)

    def test_id_deidentification(self):
        """
        Verify that household IDs are successfully salted and hashed, ensuring 
        determinism for joining but prevention of identity linkability.
        """
        df_anonymized = deidentify_metadata(self.mock_metadata, salt="TEST_SALT_123")
        
        hashed_id_1 = df_anonymized.loc[df_anonymized["occupancy_group"] == "1 (Single)", "household_id"].values[0]
        
        self.assertNotEqual(hashed_id_1, "HH_TEST_01")
        self.assertEqual(len(hashed_id_1), 16)  # We sliced hash to 16 chars

        # Test deterministic hashing
        df_anonymized_2 = deidentify_metadata(self.mock_metadata, salt="TEST_SALT_123")
        hashed_id_2 = df_anonymized_2.loc[df_anonymized_2["occupancy_group"] == "1 (Single)", "household_id"].values[0]
        self.assertEqual(hashed_id_1, hashed_id_2)

        # Test salt difference
        df_anonymized_diff_salt = deidentify_metadata(self.mock_metadata, salt="DIFFERENT_SALT_456")
        hashed_id_diff = df_anonymized_diff_salt.loc[df_anonymized_diff_salt["occupancy_group"] == "1 (Single)", "household_id"].values[0]
        self.assertNotEqual(hashed_id_1, hashed_id_diff)

    def test_differential_privacy_noise(self):
        """
        Validate that the Laplace mechanism successfully injects noise and that 
        smaller epsilon budgets result in higher noise variance (higher privacy protection).
        """
        np.random.seed(42)
        base_value = 22.5  # average temp
        sensitivity = 2.0  # max expected temp variance
        
        # For a high epsilon (low privacy), noise should be very small
        high_eps_runs = [LaplaceDP.add_laplace_noise(base_value, sensitivity, epsilon=100.0) for _ in range(100)]
        high_eps_variance = np.var(high_eps_runs)
        
        # For a low epsilon (high privacy), noise should be significantly larger
        low_eps_runs = [LaplaceDP.add_laplace_noise(base_value, sensitivity, epsilon=0.1) for _ in range(100)]
        low_eps_variance = np.var(low_eps_runs)
        
        print(f"\nDP Test - High Epsilon Var: {high_eps_variance:.6f}, Low Epsilon Var: {low_eps_variance:.6f}")
        self.assertTrue(low_eps_variance > high_eps_variance)
        
        # Check that private_mean operates correctly
        data = pd.Series([20.0, 21.0, 22.0, 23.0, 24.0])
        priv_mean = LaplaceDP.private_mean(data, val_range=(15.0, 30.0), epsilon=10.0)
        self.assertNotEqual(priv_mean, 22.0)  # should not equal exact mean due to noise addition
        self.assertTrue(15.0 <= priv_mean <= 30.0)  # should fall in logical domain

    def test_clean_data_pipeline_integrity(self):
        """
        Verify the output files from running the clean_and_store_data pipeline.
        Assert that there are no remaining missing values and schemas match.
        """
        # Execute cleaning function
        df_clean = clean_and_store_data()
        
        # Check output structure and null constraints
        self.assertFalse(df_clean.isna().any().any(), "Cleaned dataset contains NaN values!")
        self.assertIn("power_zscore", df_clean.columns)
        self.assertIn("temperature_zscore", df_clean.columns)
        self.assertIn("occupancy_group", df_clean.columns)
        
        # Assert no direct PII exists in columns
        self.assertNotIn("owner_name", df_clean.columns)
        self.assertNotIn("street_address", df_clean.columns)

    def test_database_persistence(self):
        """
        Verify that database writing creates the correct tables and records
        with proper relational integrity and no raw IDs.
        """
        self.assertTrue(os.path.exists(self.db_path), "SQLite database was not created!")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Query tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        self.assertIn("dim_households", tables)
        self.assertIn("fact_sensor_logs", tables)
        
        # Check fact logs row count
        cursor.execute("SELECT COUNT(*) FROM fact_sensor_logs;")
        fact_count = cursor.fetchone()[0]
        self.assertEqual(fact_count, 12096)  # 3 households * 14 days * 288 records/day
        
        # Check that household IDs are hashed (16 characters) in the DB
        cursor.execute("SELECT DISTINCT household_id FROM fact_sensor_logs;")
        db_ids = [r[0] for r in cursor.fetchall()]
        for hid in db_ids:
            self.assertEqual(len(hid), 16)
            self.assertFalse(hid.startswith("HH_"))
            
        conn.close()

if __name__ == "__main__":
    unittest.main()
