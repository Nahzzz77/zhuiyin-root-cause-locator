#!/usr/bin/env python3
"""Tiny local web shell for the bug-location MVP."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from analyzer import analyze


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
MAX_BODY_BYTES = 64 * 1024
# ponytail: one in-flight analysis per local process; add a queue only for real multi-user demand.
ANALYSIS_LOCK = threading.Lock()


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], repo_path: Path):
        super().__init__(address, DemoHandler)
        self.repo_path = repo_path


class DemoHandler(BaseHTTPRequestHandler):
    server: DemoServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"ok": True})
            return
        if path == "/api/config":
            self._json(
                {
                    "repo_name": self.server.repo_path.name,
                    "repo_path": str(self.server.repo_path),
                    "read_only": True,
                    "demo_input": {
                        "bug_report": "用户取消使用优惠券的订单后，再次下单仍提示优惠券已使用，无法重新使用。",
                        "expected_result": "订单取消成功后，应退还该订单占用的优惠券，使用户可以再次使用。",
                        "reproduction_steps": "1. 用户领取优惠券并下单；2. 订单创建成功；3. 用户取消订单；4. 再次下单选择同一优惠券时提示已使用。",
                    },
                }
            )
            return
        self._static("index.html" if path == "/" else path.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/analyze":
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
            if payload.get("source_consent") is not True:
                self._json(
                    {
                        "error": "必须明确同意将授权源码发送给模型分析",
                        "hint": "请将 source_consent 设置为 true 后重试。",
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return
            bug_report = self._text(payload, "bug_report", required=True, limit=4_000)
            expected = self._text(payload, "expected_result", limit=2_000)
            steps = self._text(payload, "reproduction_steps", limit=4_000)
            if not ANALYSIS_LOCK.acquire(blocking=False):
                self._json(
                    {
                        "error": "已有分析任务正在运行",
                        "hint": "当前本地 MVP 同时只运行一个分析，请稍后重试。",
                    },
                    HTTPStatus.TOO_MANY_REQUESTS,
                )
                return
            try:
                result = analyze(
                    repo_path=self.server.repo_path,
                    bug_report=bug_report,
                    expected_result=expected,
                    reproduction_steps=steps,
                )
            finally:
                ANALYSIS_LOCK.release()
            self._json(result)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except TimeoutError as exc:
            self._json({"error": str(exc)}, HTTPStatus.GATEWAY_TIMEOUT)
        except Exception as exc:  # keep the demo honest instead of returning fake findings
            print(f"analysis failed: {exc!r}", file=sys.stderr)
            self._json(
                {"error": f"分析失败：{exc}", "hint": "确认 Codex 已登录后重试。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _read_json(self) -> dict[str, object]:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("请求长度无效") from exc
        if not 0 < size <= MAX_BODY_BYTES:
            raise ValueError("请求为空或过大")
        try:
            value = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求不是有效 JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("请求必须是 JSON 对象")
        return value

    @staticmethod
    def _text(
        payload: dict[str, object], key: str, *, required: bool = False, limit: int
    ) -> str:
        value = payload.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"{key} 必须是文本")
        value = value.strip()
        if required and not value:
            raise ValueError("请先填写 Bug 现象")
        if len(value) > limit:
            raise ValueError(f"{key} 最多 {limit} 个字符")
        return value

    def _static(self, relative: str) -> None:
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT not in candidate.parents or not candidate.is_file():
            self._json({"error": "页面不存在"}, HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="业务 Bug 到代码根因排查 MVP")
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT / "sample_repo",
        help="授权读取的 Python 代码目录，默认使用内置优惠券示例",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"代码目录不存在：{repo}")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("端口必须在 1024 到 65535 之间")

    server = DemoServer(("127.0.0.1", args.port), repo)
    url = f"http://127.0.0.1:{args.port}"
    print(f"追因已启动：{url}")
    print(f"只读代码目录：{repo}")
    print("按 Ctrl+C 停止。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
