from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GTSTTripIndependenceTests(unittest.TestCase):
    def test_wrapper_publishes_distinct_latches_and_assert_times(self) -> None:
        source = (ROOT / "modelica" / "TripLens_CombinedCycle_TripTAC.mo.tpl").read_text(
            encoding="utf-8"
        )
        self.assertIn("vppGTTripLatch = vppGTTripLatchInternal", source)
        self.assertNotIn("vppGTTripLatch = vppSTTripLatch", source)
        self.assertIn("when edge(vppGTTripLatch)", source)
        self.assertIn("when edge(vppSTTripLatchPublished)", source)
        self.assertIn("vppGTTripAssertTime = time", source)
        self.assertIn("vppSTTripAssertTime = time", source)
        self.assertIn(
            "time >= vppSTTripAssertTime + vppSTBreakerOpenDelay",
            source,
        )


if __name__ == "__main__":
    unittest.main()
