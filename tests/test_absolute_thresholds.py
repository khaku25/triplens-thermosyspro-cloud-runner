import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AbsoluteThresholdContractTests(unittest.TestCase):
    def test_runtime_rules_use_only_absolute_or_boolean(self):
        with (ROOT / "config" / "dcs_alarm_rules.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 30)
        self.assertLessEqual(
            {row["threshold_mode"] for row in rows}, {"ABSOLUTE", "BOOLEAN"}
        )
        self.assertTrue(all(row["unit"] for row in rows))
        self.assertTrue(all(float(row["hysteresis_value"]) >= 0 for row in rows))

    def test_no_ratio_field_in_runtime_schema(self):
        header = (
            ROOT / "config" / "dcs_alarm_rules.csv"
        ).read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertNotIn("hysteresis_ratio", header)
        self.assertIn("hysteresis_value", header)


if __name__ == "__main__":
    unittest.main()
