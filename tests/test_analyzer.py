from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analyzer


def model_result(file: str = "good.py", start: int = 2, end: int = 2) -> dict:
    return {
        "summary": "取消路径没有恢复状态。",
        "findings": [
            {
                "file": file,
                "start_line": start,
                "end_line": end,
                "title": "状态没有回滚",
                "confidence": "high",
                "reason": "取消后直接返回。",
                "evidence": "return coupon.used",
                "cause_chain": ["取消订单", "未释放优惠券", "再次使用失败"],
                "fix_suggestion": "恢复优惠券状态。",
                "verification": "取消后再次下单。",
            }
        ],
    }


class AnalyzerTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        (repo / "good.py").write_text(
            "def cancel_order(coupon):\n    return coupon.used\n", encoding="utf-8"
        )
        for name in (".git", ".venv", "node_modules", ".hidden"):
            hidden = repo / name
            hidden.mkdir()
            (hidden / "ignored.py").write_text("raise RuntimeError\n", encoding="utf-8")
        return repo

    @staticmethod
    def codex_response(payload: dict):
        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        return fake_run

    def test_analyze_scans_only_allowed_python_and_returns_validated_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repo = self.make_repo(Path(temp_name))
            with patch("analyzer.shutil.which", return_value="/usr/bin/codex"), patch(
                "analyzer.subprocess.run", side_effect=self.codex_response(model_result())
            ) as run:
                result = analyzer.analyze(repo, "取消订单后优惠券无法再使用")

        self.assertEqual(result["provider"], "codex-exec")
        self.assertEqual(result["scanned_files"], ["good.py"])
        self.assertEqual(result["findings"][0]["file"], "good.py")
        command = run.call_args.args[0]
        self.assertIn("read-only", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("取消订单", run.call_args.kwargs["input"])

    def test_discards_paths_outside_repo_and_nonexistent_lines(self) -> None:
        invalid = {
            "summary": "含无效引用。",
            "findings": [
                model_result("../outside.py", 1, 1)["findings"][0],
                model_result("good.py", 99, 99)["findings"][0],
                model_result("good.py", 1, 1)["findings"][0],
            ],
        }
        with tempfile.TemporaryDirectory() as temp_name:
            repo = self.make_repo(Path(temp_name))
            with patch("analyzer.shutil.which", return_value="/usr/bin/codex"), patch(
                "analyzer.subprocess.run", side_effect=self.codex_response(invalid)
            ):
                result = analyzer.analyze(repo, "bug")

        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["start_line"], 1)
        self.assertTrue(any("丢弃 2 条" in note for note in result["limitations"]))

    def test_replaces_model_evidence_with_numbered_source_lines(self) -> None:
        payload = model_result("good.py", 1, 2)
        payload["findings"][0]["evidence"] = "伪造的源码证据"
        with tempfile.TemporaryDirectory() as temp_name:
            repo = self.make_repo(Path(temp_name))
            with patch("analyzer.shutil.which", return_value="/usr/bin/codex"), patch(
                "analyzer.subprocess.run", side_effect=self.codex_response(payload)
            ):
                result = analyzer.analyze(repo, "bug")

        self.assertEqual(
            result["findings"][0]["evidence"],
            "0001 | def cancel_order(coupon):\n0002 |     return coupon.used",
        )

    def test_explicit_scripted_fallback_is_clearly_marked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repo = self.make_repo(Path(temp_name))
            with patch.dict(os.environ, {analyzer.FALLBACK_ENV: "force"}), patch(
                "analyzer.subprocess.run"
            ) as run:
                result = analyzer.analyze(repo, "取消订单后优惠券仍为已使用")

        run.assert_not_called()
        self.assertEqual(result["provider"], "scripted-fallback-demo-only")
        self.assertTrue(result["findings"])
        self.assertTrue(any("不是 AI 分析" in note for note in result["limitations"]))


if __name__ == "__main__":
    unittest.main()
