from __future__ import annotations

import io
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import server


class ServerTests(unittest.TestCase):
    def post(self, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        body = json.dumps(payload).encode()
        handler = object.__new__(server.DemoHandler)
        handler.path = "/api/analyze"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace(repo_path=Path(__file__).parent)
        responses: list[tuple[int, dict[str, object]]] = []
        handler._json = lambda value, status=200: responses.append(
            (int(status), value)
        )
        handler.do_POST()
        self.assertEqual(len(responses), 1)
        return responses[0]

    def test_analyze_requires_explicit_source_consent(self) -> None:
        with patch("server.analyze") as analyze:
            for consent in (None, "true", 1):
                with self.subTest(consent=consent):
                    payload: dict[str, object] = {"bug_report": "bug"}
                    if consent is not None:
                        payload["source_consent"] = consent
                    status, result = self.post(payload)
                    self.assertEqual(status, 400)
                    self.assertIn("source_consent", result["hint"])
            analyze.assert_not_called()

    def test_second_analysis_is_rejected_while_first_is_running(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        first_result: list[tuple[int, dict[str, object]]] = []

        def slow_analyze(**_: object) -> dict[str, object]:
            entered.set()
            if not release.wait(timeout=2):
                raise TimeoutError("test did not release analysis")
            return {"summary": "done", "findings": []}

        with patch("server.analyze", side_effect=slow_analyze):
            first = threading.Thread(
                target=lambda: first_result.append(
                    self.post({"bug_report": "first", "source_consent": True})
                )
            )
            first.start()
            self.assertTrue(entered.wait(timeout=1))
            try:
                status, result = self.post(
                    {"bug_report": "second", "source_consent": True}
                )
                self.assertEqual(status, 429)
                self.assertIn("正在运行", result["error"])
                self.assertTrue(result["hint"])
            finally:
                release.set()
                first.join(timeout=2)

        self.assertEqual(first_result[0][0], 200)


if __name__ == "__main__":
    unittest.main()
