import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "apps/web/components/TripLensWorkspace.js").read_text(encoding="utf-8")


class WorkspacePersistenceContractTest(unittest.TestCase):
    def test_workspace_mount_restores_and_persists_indexeddb_session(self):
        self.assertIn("loadSession", WORKSPACE)
        self.assertIn("saveSession", WORKSPACE)
        self.assertIn("buildWorkspaceSession", WORKSPACE)
        self.assertIn("canRestoreWorkspaceSession", WORKSPACE)
        self.assertIn("loadSession()", WORKSPACE)
        self.assertIn("saveSession(buildWorkspaceSession", WORKSPACE)


    def test_workspace_mount_does_not_clear_session_before_restoration(self):
        self.assertNotIn("clearSession().catch(()=>{});\n    let active=true;", WORKSPACE)
        self.assertIn("const [restored,setRestored]=useState(false);", WORKSPACE)


if __name__ == "__main__":
    unittest.main()
