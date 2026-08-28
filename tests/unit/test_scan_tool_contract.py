import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIONS_PY = ROOT / "src" / "omnibot" / "actions.py"


class ScanRemovedContractTests(unittest.TestCase):
    def test_scan_function_does_not_exist_in_actions(self):
        source = ACTIONS_PY.read_text(encoding="utf-8")
        self.assertNotIn("def scan(", source)

    def test_snapshot_collect_interaction_metadata_returns_visible_elements(self):
        from omnibot import snapshot

        class Driver:
            pass

        def fake_evaluate(driver, tab_id, expression, token=None):
            assert "querySelectorAll" in expression
            return [{"index": 0, "tag": "button", "label": "Submit", "visible": True, "box": {"x": 1, "y": 2, "width": 3, "height": 4}}]

        import unittest.mock as mock
        with mock.patch("omnibot.cdp.evaluate", fake_evaluate):
            result = snapshot.collect_interaction_metadata(Driver(), "tab-1")

        self.assertEqual(result, {"elements": [{"index": 0, "tag": "button", "label": "Submit", "visible": True, "box": {"x": 1, "y": 2, "width": 3, "height": 4}}]})


if __name__ == "__main__":
    unittest.main()
