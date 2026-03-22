"""Tests for the synthetic sensitivity dataset generator."""

import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from generate_synthetic_data import DEPARTMENT_TARGETS, LABEL_DISTRIBUTION, OUTPUT_COLUMNS, generate_dataset


class GenerateSyntheticDataTests(unittest.TestCase):
    """Validate dataset generation and export behavior."""

    def test_generate_dataset_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            splits = generate_dataset(Path(tmp_dir), seed=11)

            self.assertEqual(
                {name: len(rows) for name, rows in splits.items()},
                {"train": 980, "val": 210, "test": 210},
            )

            expected_files = [
                Path(tmp_dir) / "sensitive_dataset_train.csv",
                Path(tmp_dir) / "sensitive_dataset_val.csv",
                Path(tmp_dir) / "sensitive_dataset_test.csv",
                Path(tmp_dir) / "processed" / "sensitive_dataset_train.jsonl",
                Path(tmp_dir) / "processed" / "sensitive_dataset_val.jsonl",
                Path(tmp_dir) / "processed" / "sensitive_dataset_test.jsonl",
            ]
            for path in expected_files:
                self.assertTrue(path.exists())

    def test_generated_rows_match_schema_and_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            splits = generate_dataset(Path(tmp_dir), seed=11)
            combined = [row for rows in splits.values() for row in rows]

            self.assertEqual(Counter(row.label for row in combined), LABEL_DISTRIBUTION)
            self.assertEqual(Counter(row.department for row in combined), DEPARTMENT_TARGETS)

            csv_path = Path(tmp_dir) / "sensitive_dataset_train.csv"
            with csv_path.open(encoding="utf-8") as handle:
                header = handle.readline().strip().split(",")
                first_row = handle.readline().strip()

            self.assertEqual(header, OUTPUT_COLUMNS)
            self.assertTrue(first_row)

            jsonl_path = Path(tmp_dir) / "processed" / "sensitive_dataset_train.jsonl"
            with jsonl_path.open(encoding="utf-8") as handle:
                record = json.loads(handle.readline())

            self.assertEqual(list(record.keys()), OUTPUT_COLUMNS)
            self.assertIsInstance(record["contains"], list)


if __name__ == "__main__":
    unittest.main()
