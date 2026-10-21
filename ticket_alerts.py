#!/usr/bin/env python3
"""
Free Multi-Channel Ticket Alert System for NorCal Ren Faire (Sat, Oct 24, 2026).
Supports:
1. Free Carrier Email-to-SMS Gateways (@vtext.com, @txt.att.net, @tmomail.net, etc.) + Direct Email via SMTP
2. Textbelt Free SMS API fallback (https://textbelt.com/text)
3. Instant Mobile & Web Push via ntfy.sh (https://ntfy.sh/norcal_renfaire_oct24_tickets)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ALERT_CONFIG_FILE = Path("alert_config.json")
NTFY_ALERT_TOPIC = "norcal_renfaire_oct24_tickets"
NTFY_ALERT_URL = f"https://ntfy.sh/{NTFY_ALERT_TOPIC}"

CARRIER_GATEWAYS: dict[str, str] = {
    "verizon": "vtext.com",
    "att": "txt.att.net",
    "tmobile": "tmomail.net",
    "mint": "tmomail.net",
    "cricket": "mms.cricketwireless.net",
    "boost": "sms.myboostmobile.com",
    "googlefi": "msg.fi.google.com",
    "uscellular": "email.uscc.net",
    "xfinity": "vtext.com",
    "visible": "vtext.com",
}


def normalize_phone(phone: str) -> str:
    """Extract a 10-digit US phone number from user input."""
    digits = re.sub(r"\D+", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if not digits:
        return ""
    return f"(•••) •••-{digits[-4:]}"


def mask_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "•••"
    else:
        masked_local = local[:1] + "•••" + local[-1:]
    return f"{masked_local}@{domain}"


def subscriber_id(phone: str, email: str, name: str) -> str:
    raw = f"{normalize_phone(phone)}|{(email or '').strip().lower()}|{(name or '').strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]


def load_alert_config() -> dict[str, str]:
    cfg: dict[str, str] = {
        "smtp_host": os.environ.get("RENFAIRE_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": os.environ.get("RENFAIRE_SMTP_PORT", "465"),
        "smtp_email": os.environ.get("RENFAIRE_SMTP_EMAIL", ""),
        "smtp_password": os.environ.get("RENFAIRE_SMTP_PASSWORD", ""),
        "textbelt_key": os.environ.get("RENFAIRE_TEXTBELT_KEY", "textbelt"),
    }
    if ALERT_CONFIG_FILE.exists():
        try:
            file_cfg = json.loads(ALERT_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(file_cfg, dict):
                for k, v in file_cfg.items():
                    if v:
                        cfg[k] = str(v)
        except Exception:
            pass
    return cfg


def send_ntfy_push(title: str, message: str, click_url: str = "https://slizha99.github.io/renfaire-ticket-scout/") -> bool:
    """Publish an instant push alert to https://ntfy.sh/norcal_renfaire_oct24_tickets."""
    try:
        headers = {
            "Title": title[:120],
            "Priority": "high",
            "Tags": "ticket,castle",
        }
        if click_url and click_url.startswith("http"):
            headers["Click"] = click_url
        req = urllib.request.Request(
            NTFY_ALERT_URL,
            data=message.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_smtp_message(to_addr: str, subject: str, body: str, config: dict[str, str] | None = None) -> bool:
    """Send an email or Email-to-SMS gateway message via SMTP if configured."""
    cfg = config or load_alert_config()
    smtp_email = cfg.get("smtp_email", "").strip()
    smtp_password = cfg.get("smtp_password", "").strip().replace(" ", "")
    if not smtp_email or not smtp_password or not to_addr:
        return False

    msg = EmailMessage()
    msg["From"] = smtp_email
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    host = cfg.get("smtp_host", "smtp.gmail.com")
    port = int(cfg.get("smtp_port", "465") or 465)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def send_textbelt_sms(phone: str, message: str, config: dict[str, str] | None = None) -> bool:
    """Attempt SMS delivery via Textbelt (supports the free 'textbelt' key or a paid key)."""
    digits = normalize_phone(phone)
    if not digits:
        return False
    cfg = config or load_alert_config()
    key = cfg.get("textbelt_key", "textbelt") or "textbelt"
    try:
        data = urllib.parse.urlencode({
            "phone": digits,
            "message": message[:155],
            "key": key,
        }).encode("utf-8")
        req = urllib.request.Request("https://textbelt.com/text", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            res = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(res.get("success"))
    except Exception:
        return False


def notify_single_subscriber(sub: dict[str, Any], subject: str, short_sms: str, full_body: str, config: dict[str, str] | None = None) -> dict[str, bool]:
    """Send an alert to a single subscriber across their configured SMS gateway, Textbelt, and Email."""
    cfg = config or load_alert_config()
    results = {"carrier_sms": False, "textbelt_sms": False, "email": False}

    phone = normalize_phone(str(sub.get("phone", "")))
    carrier = str(sub.get("carrier", "")).strip().lower()
    email = str(sub.get("email", "")).strip()

    if phone:
        gateway = CARRIER_GATEWAYS.get(carrier)
        if gateway:
            sms_addr = f"{phone}@{gateway}"
            results["carrier_sms"] = send_smtp_message(sms_addr, "", short_sms, cfg)
        if not results["carrier_sms"]:
            results["textbelt_sms"] = send_textbelt_sms(phone, short_sms, cfg)

    if email and "@" in email:
        results["email"] = send_smtp_message(email, subject, full_body, cfg)

    return results


def broadcast_new_ticket_alerts(listings: list[Any], subscribers: list[dict[str, Any]]) -> int:
    """
    Broadcast alerts for newly discovered LOW/MEDIUM risk Saturday Oct 24 listings
    to ntfy.sh push subscribers AND all registered SMS/Email subscribers.
    Returns total notifications dispatched.
    """
    if not listings:
        return 0

    cfg = load_alert_config()
    dispatched = 0

    for item in listings:
        # Support both TicketListing dataclass and dict
        plat = getattr(item, "platform", None) or (item.get("platform") if isinstance(item, dict) else "Listing")
        title = getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else "New Ticket")
        url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else "https://slizha99.github.io/renfaire-ticket-scout/")
        price_val = getattr(item, "price_usd", None) if not isinstance(item, dict) else item.get("price_usd")
        score = getattr(item, "scam_score", 0) if not isinstance(item, dict) else item.get("scam_score", 0)

        price_str = f"${price_val:.0f}" if price_val else "Price not listed"
        alert_title = f"🏰 Oct 24 Ren Faire Ticket ({plat}) - {price_str}"
        short_sms = f"RenFaire Oct 24 Ticket ({plat}, {price_str}, {score}% risk): {title[:65]} -> {url}"
        full_body = (
            f"New Saturday, Oct 24 NorCal Ren Faire Ticket Lead Found!\n\n"
            f"Platform: {plat}\n"
            f"Post: {title}\n"
            f"Price: {price_str}\n"
            f"Scam Score: {score}% ({'LOW RISK' if score < 35 else 'MEDIUM RISK'})\n"
            f"Direct Link: {url}\n"
            f"Shared Group Dashboard: https://slizha99.github.io/renfaire-ticket-scout/\n\n"
            f"Remember: Ask for a continuous screen recording of the Pretix/Etix order page and pay ONLY via PayPal Goods & Services."
        )

        if send_ntfy_push(alert_title, f"{title} ({price_str}, {score}% scam risk)\n{url}", click_url=str(url)):
            dispatched += 1

        for sub in subscribers:
            res = notify_single_subscriber(sub, alert_title, short_sms, full_body, cfg)
            if any(res.values()):
                dispatched += 1

    return dispatched
