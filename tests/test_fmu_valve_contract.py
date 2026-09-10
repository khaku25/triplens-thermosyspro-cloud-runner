from __future__ import annotations

import csv
import importlib.util
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_fmu_valve_contract", ROOT / "scripts" / "build_fmu_valve_contract.py"
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class FmuValveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = module.read_inventory()
        cls.ports = module.make_port_rows(cls.inventory)
        cls.logic = module.make_logic_rows(cls.inventory)

    def test_inventory_contains_only_the_twelve_native_valves(self):
        self.assertEqual(len(self.inventory), 12)
        self.assertEqual(
            {row["native_object"] for row in self.inventory},
            module.EXPECTED_OBJECTS,
        )
        self.assertFalse(any("A-CV-" in " ".join(row.values()) for row in self.inventory))

    def test_each_valve_has_four_inputs_and_eight_outputs(self):
        counts = Counter((row["control_point_id"], row["direction"]) for row in self.ports)
        for point in {row["control_point_id"] for row in self.inventory}:
            self.assertEqual(counts[(point, "INPUT")], 4)
            self.assertEqual(counts[(point, "OUTPUT")], 8)
        self.assertEqual(len(self.ports), 144)
        self.assertEqual(len({row["port_name"] for row in self.ports}), 144)

    def test_fault_changes_feedback_without_overwriting_command(self):
        by_type = {(row["control_point_id"], row["logic_type"]): row for row in self.logic}
        for point in {row["control_point_id"] for row in self.inventory}:
            fault = by_type[(point, "FAULT_OVERRIDE")]["expression"]
            select = by_type[(point, "CONTROL_SELECT")]["expression"]
            self.assertIn(".FB = if ", fault)
            self.assertIn(".FAULT_ENABLE then ", fault)
            self.assertIn(".FAULT_VALUE else ", fault)
            self.assertTrue(fault.endswith(".CMD"))
            self.assertNotIn(".CMD =", fault)
            self.assertIn(".CMD = if ", select)

    def test_all_ports_are_fmu_connected(self):
        self.assertEqual(
            {row["grounding_status"] for row in self.ports},
            {"FMU_CONNECTED"},
        )

    def test_committed_generated_files_are_current(self):
        module.main_check = True
        for path, fields, rows in (
            (module.PORTS, module.PORT_FIELDS, self.ports),
            (module.LOGIC, module.LOGIC_FIELDS, self.logic),
        ):
            expected = module.encode(fields, rows)
            self.assertEqual(path.read_text(encoding="utf-8"), expected)

    def test_logic_contract_size_and_status(self):
        self.assertEqual(len(self.logic), 72)
        self.assertEqual(len({row["logic_id"] for row in self.logic}), 72)
        self.assertEqual(
            {row["implementation_status"] for row in self.logic},
            {"FMU_CONNECTED"},
        )


if __name__ == "__main__":
    unittest.main()
