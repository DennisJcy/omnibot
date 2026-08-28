import unittest

from omnibot import simphtml


class ExecuteJsRichSessionTargetTest(unittest.TestCase):
    def test_post_execution_dom_diff_uses_target_session_id(self):
        session_ids = []

        class FakeDriver:
            def get_context(self, token=None):
                return object()

            def get_session_dict(self, token=None):
                return {}

            def execute_js(self, script, token=None, group_status=None, session_id=None):
                return {"data": "ok"}

        def fake_get_html(driver, *args, session_id=None, **kwargs):
            session_ids.append(session_id)
            return "<main>stable</main>"

        original_get_html = simphtml.get_html
        original_get_temp_texts = simphtml.get_temp_texts
        original_find_changed_elements = simphtml.find_changed_elements
        original_sleep = simphtml.time.sleep
        try:
            simphtml.get_html = fake_get_html
            simphtml.get_temp_texts = lambda driver, token=None: []
            simphtml.find_changed_elements = lambda before, after: {"changed": 0}
            simphtml.time.sleep = lambda seconds: None

            simphtml.execute_js_rich(
                "return 1",
                FakeDriver(),
                token="request-token",
                session_id="edge-client:555",
            )
        finally:
            simphtml.get_html = original_get_html
            simphtml.get_temp_texts = original_get_temp_texts
            simphtml.find_changed_elements = original_find_changed_elements
            simphtml.time.sleep = original_sleep

        self.assertEqual(session_ids, ["edge-client:555", "edge-client:555"])


if __name__ == "__main__":
    unittest.main()
