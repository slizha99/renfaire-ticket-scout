#!/usr/bin/env python3
"""
Interactive Collaboration Server for the NorCal Ren Faire Ticket Scout Dashboard.
Serves dashboard.html / index.html on port 8765 AND provides live API endpoints so friends can:
1. Claim a listing ("💬 I'm Messaging Seller" with their name) so multiple friends don't spam the same seller.
2. Flag / Report a seller as Suspicious/Scam ("🚨 Report Suspicious" with notes).
3. Subscribe / Unsubscribe for free instant SMS (Carrier Email-to-SMS / Textbelt), Email, and Mobile Push alerts.
"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
import threading
import urllib.parse

from ticket_alerts import (
    CARRIER_GATEWAYS,
    mask_email,
    mask_phone,
    normalize_phone,
    notify_single_subscriber,
    send_ntfy_push,
    subscriber_id,
)

STATE_FILE = Path("team_state.json")
RESULTS_FILE = Path("discovered_listings.json")
STATE_LOCK = threading.Lock()


def load_team_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("claims", {})
                data.setdefault("reports", {})
                data.setdefault("manual_leads", [])
                data.setdefault("subscribers", [])
                return data
        except Exception:
            pass
    return {"claims": {}, "reports": {}, "manual_leads": [], "subscribers": []}


def save_team_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def public_state_view(state: dict) -> dict:
    """Return team state with subscriber phone numbers and emails masked for privacy."""
    subs_public = []
    for sub in state.get("subscribers", []):
        subs_public.append({
            "id": sub.get("id", ""),
            "name": sub.get("name", "Friend"),
            "carrier": sub.get("carrier", ""),
            "masked_phone": mask_phone(sub.get("phone", "")),
            "masked_email": mask_email(sub.get("email", "")),
            "created_at": sub.get("created_at", ""),
        })
    return {
        "claims": state.get("claims", {}),
        "reports": state.get("reports", {}),
        "manual_leads": state.get("manual_leads", []),
        "subscribers": subs_public,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            state = load_team_state()
            body = json.dumps(public_state_view(state)).encode("utf-8")
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

        extra_resp: dict = {}

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

            elif parsed.path == "/api/subscribe":
                name = str(payload.get("name", "")).strip() or "Friend"
                phone = normalize_phone(str(payload.get("phone", "")))
                carrier = str(payload.get("carrier", "")).strip().lower()
                email = str(payload.get("email", "")).strip()

                if not phone and ("@" not in email):
                    extra_resp = {"ok": False, "error": "Please enter a valid 10-digit US phone number or an email address."}
                elif phone and carrier and carrier not in CARRIER_GATEWAYS and carrier != "none":
                    extra_resp = {"ok": False, "error": f"Unsupported carrier '{carrier}'."}
                else:
                    sub_id = subscriber_id(phone, email, name)
                    subs = [s for s in state.get("subscribers", []) if s.get("id") != sub_id]
                    new_sub = {
                        "id": sub_id,
                        "name": name,
                        "phone": phone,
                        "carrier": carrier if phone else "",
                        "email": email,
                        "created_at": now_str,
                    }
                    subs.append(new_sub)
                    state["subscribers"] = subs
                    save_team_state(state)

                    # Send welcome alert in background thread so HTTP response is immediate
                    def _welcome(s: dict) -> None:
                        short_msg = f"🏰 Hi {s['name']}! You're subscribed to Sat Oct 24 NorCal Ren Faire ticket alerts."
                        full_msg = (
                            f"Hi {s['name']}!\n\n"
                            f"You are now subscribed to instant ticket alerts for Saturday, October 24, 2026 "
                            f"Northern California Renaissance Faire tickets.\n\n"
                            f"Live Board: https://slizha99.github.io/renfaire-ticket-scout/\n"
                            f"Instant Push Topic: https://ntfy.sh/norcal_renfaire_oct24_tickets"
                        )
                        notify_single_subscriber(s, "🏰 Subscribed: NorCal Ren Faire Ticket Alerts", short_msg, full_msg)
                        send_ntfy_push(
                            "🏰 New Ticket Alert Subscriber",
                            f"{s['name']} subscribed to Saturday Oct 24 Ren Faire ticket alerts!",
                        )

                    threading.Thread(target=_welcome, args=(new_sub,), daemon=True).start()
                    extra_resp = {"ok": True, "subscribed": public_state_view({"subscribers": [new_sub]})["subscribers"][0]}

            elif parsed.path == "/api/unsubscribe":
                target_id = str(payload.get("id", "")).strip()
                before = len(state.get("subscribers", []))
                state["subscribers"] = [
                    s for s in state.get("subscribers", [])
                    if s.get("id") != target_id
                ]
                save_team_state(state)
                extra_resp = {"ok": True, "removed": before - len(state["subscribers"])}

        resp_data = {"ok": True, "state": public_state_view(state)}
        resp_data.update(extra_resp)
        body = json.dumps(resp_data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    print("Serving interactive ticket scout dashboard on http://127.0.0.1:8765 ...")
    server.serve_forever()
