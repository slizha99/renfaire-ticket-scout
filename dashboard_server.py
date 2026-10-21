#!/usr/bin/env python3
"""
Interactive Collaboration Server for the NorCal Ren Faire Ticket Scout Dashboard.
Serves dashboard.html / index.html on port 8765 AND provides live API endpoints so friends can:
1. Claim a listing ("💬 I'm Messaging Seller" with their name) so multiple friends don't spam the same seller.
2. Flag / Report a seller as Suspicious/Scam ("🚨 Report Suspicious" with notes).
3. Manually add a DM / seller lead to the shared board for the group to see.
"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
import threading
import urllib.parse

STATE_FILE = Path("team_state.json")
RESULTS_FILE = Path("discovered_listings.json")
STATE_LOCK = threading.Lock()


def load_team_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"claims": {}, "reports": {}, "manual_leads": []}


def save_team_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            state = load_team_state()
            body = json.dumps(state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in ("/", "/index.html", "/dashboard.html"):
            self.path = "/dashboard.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}

        with STATE_LOCK:
            state = load_team_state()
            now_str = datetime.now().strftime("%I:%M %p")

            if parsed.path == "/api/claim":
                item_id = str(payload.get("id", "")).strip()
                who = str(payload.get("name", "")).strip()
                status = str(payload.get("status", "Messaging Seller")).strip()
                if item_id:
                    if not who:
                        state["claims"].pop(item_id, None)
                    else:
                        state["claims"][item_id] = {
                            "name": who,
                            "status": status,
                            "updated_at": now_str,
                        }
                    save_team_state(state)

            elif parsed.path == "/api/report":
                item_id = str(payload.get("id", "")).strip()
                reporter = str(payload.get("name", "Friend")).strip() or "Friend"
                reason = str(payload.get("reason", "Suspicious behavior")).strip()
                if item_id:
                    reports_list = state["reports"].get(item_id, [])
                    reports_list.append({
                        "reporter": reporter,
                        "reason": reason,
                        "time": now_str,
                    })
                    state["reports"][item_id] = reports_list
                    save_team_state(state)

            elif parsed.path == "/api/clear_report":
                item_id = str(payload.get("id", "")).strip()
                if item_id and item_id in state["reports"]:
                    state["reports"].pop(item_id, None)
                    save_team_state(state)

        body = json.dumps({"ok": True, "state": state}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    print("Serving interactive ticket scout dashboard on http://127.0.0.1:8765 ...")
    server.serve_forever()
