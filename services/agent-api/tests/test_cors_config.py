from __future__ import annotations

import sys
import unittest
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[1]
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from triplens.cors_config import DEFAULT_WEB_ORIGINS, web_origins


class CorsConfigTest(unittest.TestCase):
    def test_review_preview_origins_are_allowed(self):
        origins = web_origins()
        self.assertIn(
            "https://triplens-web-preview-pvb6ms2t5-junsic-s-projects.vercel.app",
            origins,
        )
        self.assertIn(
            "https://triplens-web-preview-git-codex-analysi-cb9b23-junsic-s-projects.vercel.app",
            origins,
        )
        self.assertEqual(len(origins), len(set(origins)))
        self.assertEqual(len(DEFAULT_WEB_ORIGINS), len(set(DEFAULT_WEB_ORIGINS)))

    def test_configured_origin_is_added_once(self):
        origin = "https://review.example.com"
        self.assertEqual(web_origins(origin).count(origin), 1)


if __name__ == "__main__":
    unittest.main()
