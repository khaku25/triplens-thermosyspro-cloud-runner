from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_native_opcua_valve_contract",
    ROOT / "scripts" / "build_native_opcua_valve_contract.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class NativeOpcuaValveNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = module.read_inventory()
        cls.nodes = module.make_node_rows(cls.inventory)
        cls.logic = module.make_logic_rows(cls.inventory)

    def test_exactly_twelve_valves_and_144_unique_native_nodes(self) -> None:
        self.assertEqual(len(self.inventory), 12)
        self.assertEqual(len(self.nodes), 144)
        self.assertEqual(len({row["canonical_tag"] for row in self.nodes}), 144)
        self.assertEqual(len({row["opcua_browse_name"] for row in self.nodes}), 144)
        self.assertTrue(
            all(str(row["opcua_browse_name"]).startswith("vppVlv") for row in self.nodes)
        )

    def test_each_valve_has_four_writes_and_eight_reads(self) -> None:
        counts = Counter((row["control_point_id"], row["direction"]) for row in self.nodes)
        for point in module.POINT_SUFFIXES:
            self.assertEqual(counts[(point, "WRITE")], 4)
            self.assertEqual(counts[(point, "READ")], 8)

    def test_native_write_transport_is_real_and_boolean_semantics_are_explicit(self) -> None:
        writes = [row for row in self.nodes if row["direction"] == "WRITE"]
        self.assertEqual(len(writes), 48)
        self.assertTrue(all(row["data_type"] == "Real" for row in writes))
        self.assertTrue(all(row["writable"] == 1 for row in writes))
        bool_roles = {"AUTO_MAN_SELECT", "FAULT_ENABLE"}
        self.assertTrue(
            all(
                row["semantic_type"] == "Boolean"
                for row in writes
                if row["role"] in bool_roles
            )
        )

    def test_outputs_include_all_eight_physical_and_control_feedback_roles(self) -> None:
        expected = {
            "AUTOMATIC_COMMAND",
            "SELECTED_COMMAND",
            "APPLIED_POSITION",
            "COMMAND_FEEDBACK_DEVIATION",
            "FAULT_STATUS",
            "SOLVED_CV",
            "SOLVED_MASS_FLOW",
            "SOLVED_PRESSURE_DROP",
        }
        for point in module.POINT_SUFFIXES:
            actual = {
                row["role"]
                for row in self.nodes
                if row["control_point_id"] == point and row["direction"] == "READ"
            }
            self.assertEqual(actual, expected)

    def test_contract_is_native_only_and_generated_files_are_current(self) -> None:
        self.assertEqual(
            {row["implementation_status"] for row in self.nodes},
            {"NATIVE_OPCUA_CONNECTED"},
        )
        encoded_nodes = module.encode(module.NODE_FIELDS, self.nodes)
        encoded_logic = module.encode(module.LOGIC_FIELDS, self.logic)
        self.assertNotIn("FMU.", encoded_nodes)
        self.assertNotIn("fmuVlv", encoded_nodes)
        self.assertNotIn("FMU_", encoded_logic)
        self.assertEqual(module.NODES.read_text(encoding="utf-8"), encoded_nodes)
        self.assertEqual(module.LOGIC.read_text(encoding="utf-8"), encoded_logic)

    def test_logic_contract_preserves_fault_and_deviation_semantics(self) -> None:
        self.assertEqual(len(self.logic), 72)
        by_type = Counter(row["logic_type"] for row in self.logic)
        self.assertEqual(by_type["CONTROL_SELECT"], 12)
        self.assertEqual(by_type["FAULT_OVERRIDE"], 12)
        self.assertEqual(by_type["ALARM"], 12)
        for row in self.logic:
            self.assertEqual(row["implementation_status"], "NATIVE_OPCUA_CONNECTED")


if __name__ == "__main__":
    unittest.main()
