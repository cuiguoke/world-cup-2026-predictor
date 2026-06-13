#!/usr/bin/env python3
"""
Local web app for the World Cup AI Predictor MVP.

Phase 1 intentionally uses only Python's standard library. It serves a small
single-page app and exposes basic JSON APIs for status and official groups.
"""

from __future__ import annotations

import json
import mimetypes
import socket
import sys
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from app_config import (
    ALLOW_USER_SCORE_INPUT,
    APP_MODE,
    FULL_RESULTS_PATH,
    GROUPS_PATH,
    REPORTS_ROOT,
    ROOT,
    SAMPLE_RESULTS_PATH,
    WEB_ROOT,
)
from services.llm import llm_status, public_llm_config, test_llm_connection
from services.prediction import run_prediction
from services.report import generate_report
from services.schedule import load_or_create_matches, save_user_match_overrides
from services.sources import (
    create_source,
    delete_source,
    enriched_factors,
    extract_factors,
    load_sources,
)
from services.teams import load_team_names, localize_groups, localize_matches
from storage import app_log, read_json
from worldcup_simulator import load_groups


def app_status() -> dict[str, object]:
    groups_ok = GROUPS_PATH.exists()
    team_count = 0
    if groups_ok:
        groups = read_json(GROUPS_PATH)
        team_count = sum(len(teams) for teams in groups.values())
    results_path = FULL_RESULTS_PATH if FULL_RESULTS_PATH.exists() else SAMPLE_RESULTS_PATH

    return {
        "app": "2026 世界杯 AI 预测助手",
        "phase": "MVP Phase 5",
        "groupsLoaded": groups_ok,
        "teamCount": team_count,
        "llmStatus": llm_status(),
        "appMode": APP_MODE,
        "allowUserScoreInput": ALLOW_USER_SCORE_INPUT,
        "dataMode": "official_groups_full_history" if results_path == FULL_RESULTS_PATH else "official_groups_sample_results",
        "historySource": str(results_path.relative_to(ROOT)),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "WorldCupAIPredictor/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self) -> object:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.get", path=path)

        if path == "/api/status":
            self.send_json(app_status())
            return

        if path == "/api/groups":
            if not GROUPS_PATH.exists():
                self.send_json({"error": "groups_2026.json not found"}, HTTPStatus.NOT_FOUND)
                return
            groups = load_groups(GROUPS_PATH)
            self.send_json({"groups": localize_groups(groups), "teamNames": load_team_names()})
            return

        if path == "/api/matches":
            self.send_json({"matches": localize_matches(load_or_create_matches())})
            return

        if path == "/api/llm/config":
            self.send_json(public_llm_config())
            return

        if path == "/api/sources":
            self.send_json({"sources": load_sources()})
            return

        if path == "/api/factors":
            self.send_json({"factors": enriched_factors()})
            return

        if path.startswith("/reports/"):
            requested = (REPORTS_ROOT / path.removeprefix("/reports/")).resolve()
            if REPORTS_ROOT not in requested.parents and requested != REPORTS_ROOT:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self.send_file(requested)
            return

        if path in {"/", "/index.html"}:
            self.send_file(WEB_ROOT / "index.html")
            return

        requested = (WEB_ROOT / path.lstrip("/")).resolve()
        if WEB_ROOT not in requested.parents and requested != WEB_ROOT:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        self.send_file(requested)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.post", path=path)

        try:
            if path == "/api/matches":
                if not ALLOW_USER_SCORE_INPUT:
                    self.send_json({"error": "hosted 模式不允许手动录入比分"}, HTTPStatus.FORBIDDEN)
                    return
                payload = self.read_body_json()
                matches = save_user_match_overrides(list(payload.get("matches", [])))
                finished_count = sum(1 for match in matches if match.get("status") == "finished")
                app_log("matches.saved", total=len(matches), finished=finished_count)
                self.send_json({"matches": localize_matches(matches)})
                return

            if path == "/api/predict":
                payload = self.read_body_json()
                simulations = int(payload.get("simulations", 1000))
                simulations = max(100, min(simulations, 10000))
                self.send_json(run_prediction(simulations))
                return

            if path == "/api/llm/test":
                payload = self.read_body_json()
                app_log("llm.test.start", base_url=payload.get("base_url", ""), model=payload.get("model", ""))
                self.send_json(test_llm_connection(dict(payload)))
                app_log("llm.test.done", model=payload.get("model", ""))
                return

            if path == "/api/sources":
                payload = self.read_body_json()
                source = create_source(dict(payload))
                self.send_json({"source": source, "sources": load_sources()})
                return

            if path.startswith("/api/sources/") and path.endswith("/extract"):
                source_id = path.removeprefix("/api/sources/").removesuffix("/extract")
                self.send_json(extract_factors(source_id))
                return

            if path == "/api/report/generate":
                payload = self.read_body_json()
                simulations = int(payload.get("simulations", 1000))
                simulations = max(100, min(simulations, 10000))
                self.send_json(generate_report(simulations))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "API not found")
        except Exception as exc:
            app_log("http.error", path=path, error=str(exc))
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        app_log("http.delete", path=path)

        try:
            if path.startswith("/api/sources/"):
                source_id = path.removeprefix("/api/sources/")
                if not source_id or "/" in source_id:
                    self.send_error(HTTPStatus.NOT_FOUND, "API not found")
                    return
                self.send_json(delete_source(source_id))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "API not found")
        except Exception as exc:
            app_log("http.error", path=path, error=str(exc))
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free local port found.")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"World Cup AI Predictor running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
