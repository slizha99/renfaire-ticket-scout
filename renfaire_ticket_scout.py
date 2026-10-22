#!/usr/bin/env python3
"""
Northern California Renaissance Faire (Oct 24, 2026) — Full Multi-Platform Ticket Scout & Scam Scorer
Designed for Google Antigravity IDE / CLI (https://antigravity.google/) & Personal Laptop Execution

Platforms Checked:
1. Official Etix Portal (https://www.etix.com/ticket/v/13123/northern-california-renaissance-faire)
2. VouchFirst Fan-to-Fan Exchange (https://www.vouchfirst.com/home/artists/northern-california-renaissance-faire/tickets)
3. Craigslist (SF Bay Area, Monterey/Hollister, Sacramento)
4. Reddit (r/Tickets, r/TicketResale, r/SanJose, r/bayarea, r/renfaire, r/norcal, r/mountainview, r/Sacramento)
5. Vivid Seats, StubHub, and SeatGeek (JSON-LD + Playwright DOM extraction)
6. Facebook Marketplace & Vetted Community Facebook Groups:
   - Greater Bay Area Costumers Guild (GBACG): https://www.facebook.com/groups/gbacg/
   - Northern California Renaissance Faire Friends: https://www.facebook.com/groups/Renfaire/
   - Bay Area Cosplay Community: https://www.facebook.com/groups/350873855090947/
   - SF Bay Area Buy Sell Swap Marketplace: https://www.facebook.com/groups/1199093111075043/
   - California Ren Faire Friends: https://www.facebook.com/groups/CCRenFaireFriends/
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Official NorCal Ren Faire 2026 Constants (Ground Truth)
OFFICIAL_ADULT_GA_PRICE_USD = 42.0  # Includes all fees under CA SB-478
OFFICIAL_PARKING_GENERAL_USD = 12.0
OFFICIAL_PARKING_PREFERRED_USD = 30.0
TARGET_DATE_TOKENS = ("10/24", "oct 24", "october 24", "oct24", "24th", "halloween fantasy")
WRONG_DATE_TOKENS = ("10/17", "10/18", "10/10", "10/11", "10/25", "oct 10", "october 10", "oct 11", "october 11", "oct 17", "october 17", "oct 18", "october 18", "oct 25", "october 25", "sunday only")

# Target URLs
ETIX_URL = "https://www.etix.com/ticket/v/13123/northern-california-renaissance-faire"
PRETIX_URL = "https://tickets.norcalrenfaire.com/PFP/NCRF2026/"
VOUCHFIRST_URL = "https://www.vouchfirst.com/home/artists/northern-california-renaissance-faire/tickets"
VIVID_SEATS_URL = (
    "https://www.vividseats.com/northern-california-renaissance-faire-tickets--"
    "theater-arts-and-theater/performer/197252"
)
STUBHUB_URL = "https://www.stubhub.com/northern-california-renaissance-faire-tickets/grouping/150367052"
SEATGEEK_URL = "https://seatgeek.com/renaissance-faire-tickets"
FB_MARKETPLACE_URLS = [
    ("FB Marketplace (SF / Bay Area - Faire)", "https://www.facebook.com/marketplace/sanfrancisco/search?query=northern%20california%20renaissance%20faire%20tickets&sortBy=creation_time_descend"),
    ("FB Marketplace (SF / Bay Area - Fair/Casa de Fruta)", "https://www.facebook.com/marketplace/sanfrancisco/search?query=casa%20de%20fruta%20renaissance%20fair%20tickets&sortBy=creation_time_descend"),
    ("FB Marketplace (San Jose / South Bay / Hollister)", "https://www.facebook.com/marketplace/sanjose/search?query=renaissance%20faire%20tickets&sortBy=creation_time_descend"),
    ("FB Marketplace (Sacramento / Central Valley)", "https://www.facebook.com/marketplace/sacramento/search?query=renaissance%20faire%20tickets&sortBy=creation_time_descend"),
]
FB_GROUP_URLS = [
    ("FB Group: Greater Bay Area Costumers Guild (GBACG)", "https://www.facebook.com/groups/gbacg/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: NorCal Ren Faire Friends", "https://www.facebook.com/groups/Renfaire/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: SF Bay Area Buy Sell Swap", "https://www.facebook.com/groups/1199093111075043/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: NorCal Ren Faire Friends #2", "https://www.facebook.com/groups/268868156859473/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: NorCal Ren Faire Official Fan Community", "https://www.facebook.com/groups/3813768458918103/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: Renaissance & Dickens Faire Roll Call", "https://www.facebook.com/groups/313218837900/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: SF Bay Area Buy Sell Trade Donate", "https://www.facebook.com/groups/393685207478955/?sorting_setting=CHRONOLOGICAL"),
    ("FB Group: San Jose Local Marketplace", "https://www.facebook.com/groups/2172191996700376/?sorting_setting=CHRONOLOGICAL"),
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
CACHE_FILE = Path("seen_renfaire_listings.json")
RESULTS_FILE = Path("discovered_listings.json")
DASHBOARD_FILE = Path("dashboard.html")
LEARNED_KEYWORDS_FILE = Path("learned_search_terms.json")
HOLISTIC_REVIEWS_FILE = Path("holistic_reviews.json")
DEFAULT_PROFILE_DIR = Path(".antigravity_chrome_profile")

BASE_SEARCH_TERMS = [
    "renaissance faire",
    "ren faire",
    "renaissance fair",
    "ren fair",
    "casa de fruta",
    "norcal ren",
]


@dataclass
class SellerProfile:
    platform: str
    username: str
    account_age_days: int | None = None
    joined_year: int | None = None
    post_karma: int | None = None
    comment_karma: int | None = None
    has_verified_email: bool | None = None
    recent_ticket_sub_count: int = 0
    local_bay_area_signals: int = 0
    fb_rating_count: int | None = None
    is_vouched: bool | None = None
    multi_date_duplicate_posts: int = 0
    profile_url: str = ""


@dataclass
class TicketListing:
    id: str
    platform: str
    title: str
    url: str
    body: str
    posted_utc: str
    price_usd: float | None = None
    seller: SellerProfile | None = None
    scam_score: int = 0  # 0 (safe) to 100 (confirmed scam/bot)
    risk_level: str = "UNKNOWN"
    red_flags: list[str] = field(default_factory=list)
    green_flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Scam & Bot Heuristic Engine
# ---------------------------------------------------------------------------

SCAM_PAYMENT_PATTERNS = [
    (r"\b(zelle|cash\s*app|cashapp|apple\s*pay|chime|crypto|bitcoin|gift\s*card)\b", 35,
     "Requests irreversible payment method (Zelle/CashApp/Apple Pay)"),
    (r"\b(friends\s*(?:and|&)\s*family|f&f|ff\s*only|no\s*g&s|no\s*goods)\b", 45,
     "Explicitly demands Friends & Family / refuses buyer protection"),
]

SAFE_PAYMENT_PATTERNS = [
    (r"\b(paypal\s*g(?:oods)?\s*(?:and|&)?\s*s(?:ervices)?|paypal\s*g&s)\b", -25,
     "Accepts PayPal Goods & Services (covers event ticket fraud)"),
    (r"\b(meet\s*in\s*person|cash\s*in\s*person|local\s*meetup|public\s*place)\b", -20,
     "Offers in-person Bay Area / Hollister exchange"),
    (r"(tickets\.norcalrenfaire\.com/pfp/ncrf2026/order/|ncrf2026-[a-z0-9]{5}-pdf\.pdf|norcalrenfaire-ncrf-2026|change\s+details)", -30,
     "Matches authentic 2026 NorCal Ren Faire Pretix portal format (tickets.norcalrenfaire.com/PFP/NCRF2026 + 5-char order code + Change details)"),
]

BOT_PHRASE_PATTERNS = [
    (r"\b(kindly\s+dm|dm\s+me\s+if\s+interested|pm\s+me\s+for\s+details|text\s+me\s+at)\b", 20,
     "Uses generic bot reply phrasing ('kindly DM' / 'DM me if interested')"),
    (r"\b(contact\s+the\s+admin|admin\s+contact|ticket\s+assistance|group\s+admin\s+here)\b", 60,
     "Admin-run 'Ticket Assistance' scam pattern (fake Facebook group admins stealing deposits)"),
    (r"\b(fairever\s*pass|season\s*pass)\b", 50,
     "Attempts to resell a 'Fairever Pass' (strictly non-transferable; requires matching photo ID at gate)"),
    (r"\b(ticketmaster\s+transfer|axs\s+transfer|apple\s+wallet\s+transfer)\b", 40,
     "Claims Ticketmaster/AXS transfer (NorCal Ren Faire uses static Etix PDFs, not Ticketmaster)"),
    (r"\b(screenshot\s+of\s+ticket|send\s+screenshot)\b", 15,
     "Offers static screenshot proof (easily forged; ask for a continuous screen recording instead)"),
]


def stable_id_hash(text: str) -> str:
    """Deterministic SHA-1 prefix for listing IDs (avoids Python's per-process random hash() salt)."""
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def extract_price(text: str) -> float | None:
    """Extract dollar price from title or body."""
    matches = re.findall(r"\$\s*(\d{1,4}(?:\.\d{2})?)", text)
    if not matches:
        matches = re.findall(r"\b(\d{2,3})\s*(?:bucks|dollars|each|obo)\b", text, re.IGNORECASE)
    if not matches:
        return None
    prices = [float(m) for m in matches if float(m) > 5]
    return prices[0] if prices else None


HOLISTIC_SYS_PROMPT = """You are a holistic post classifier for a buyer looking ONLY for event admission tickets to the Northern California Renaissance Faire (in Hollister / Casa de Fruta, CA) that are valid for Saturday, October 24, 2026 (current date: October 21, 2026).
Read the entire post (platform, posted_utc, title, body, status_tag, and any comment audit summary) holistically as a human reader and determine if the author is OFFERING TO SELL admission tickets that could be for the Northern California Renaissance Faire on Saturday, October 24, 2026.

Reject (is_ticket_seller_for_oct24 = false) and set filter_reason using one of these TWO prefixes:
A. Prefix with "Likely Scam: " if the post/group is a scammer callout, a fake "Tickets Buy, Sell & Trade" / "GROUP ADMIN HERE" admin-middleman group, a suspiciously cheap/fake ad (e.g. "$30 tickets" with typos), or a bot/scam post targeting Faire buyers.
B. Prefix with "Irrelevant: " if the post is NOT a scam, just irrelevant to buying Saturday Oct 24 tickets:
   1. Physical item / costume / armor / props: Selling clothing, costumes, garb, armor, breastplates, gauntlets, boots, hats, swords, mugs, or crafts (even if SEO keyword spam at the bottom mentions 'ticket').
   2. Buyer / ISO post: The author is looking to buy tickets (ISO, WTB, 'Looking for tickets', asking 'Tickets for sale...?', or our own birthday party bus ISO post). Include the thread's comment audit status.
   3. Wrong Faire date / past weekend: For Oct 10, Oct 11, Oct 17, Oct 18, Sunday Oct 25, or a post written before Oct 19 saying 'for tomorrow/today/this weekend'.
   4. Wrong event / city: For a different Renaissance Faire (e.g., Las Vegas Age of Chivalry, Maryland, SoCal Irwindale, etc.).
   5. Already SOLD: Marked as SOLD or PAST.
   6. General discussion / FAQ / Admin rule reminder ('not allowed to sell tickets near the entrance').

Reply ONLY with a valid JSON object:
{"is_ticket_seller_for_oct24": boolean, "filter_reason": string or null}"""


def _load_holistic_cache() -> dict[str, dict[str, Any]]:
    if HOLISTIC_REVIEWS_FILE.exists():
        try:
            data = json.loads(HOLISTIC_REVIEWS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_holistic_cache(cache: dict[str, dict[str, Any]]) -> None:
    try:
        HOLISTIC_REVIEWS_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _holistic_cache_key(
    title: str,
    body: str,
    status_tag: str = "",
    posted_utc: str = "",
    platform: str = "",
) -> str:
    date_part = (posted_utc or "")[:10]
    norm = re.sub(r"\s+", " ", f"{date_part}|{platform}|{status_tag}|{title}|{body}".strip())[:320]
    return norm


def _call_llm_holistic_single(post_summary: str) -> tuple[bool, str | None] | None:
    """Call the LLM endpoint to holistically read the entire post and classify seller intent & eligibility."""
    try:
        payload = {
            "model": "openai",
            "messages": [
                {"role": "system", "content": HOLISTIC_SYS_PROMPT},
                {"role": "user", "content": post_summary},
            ],
        }
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=18) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"].strip()
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            verdict = json.loads(m.group(0))
            is_valid = bool(verdict.get("is_ticket_seller_for_oct24", False))
            reason = verdict.get("filter_reason")
            return is_valid, (str(reason) if reason and not is_valid else None)
    except Exception:
        pass
    return None


def analyze_post_holistically(
    title: str,
    body: str,
    status_tag: str = "",
    is_comment: bool = False,
    posted_utc: str = "",
    platform: str = "",
) -> tuple[bool, str | None]:
    """
    Holistically evaluate a post or comment using cached/live LLM reading of the entire post
    (platform, posted_utc, title, body, status_tag, and comment audit summary), with semantic fallback.
    """
    full_text = f"{title}\n{body}".strip()
    cache = _load_holistic_cache()
    ckey = _holistic_cache_key(title, body, status_tag, posted_utc, platform)
    legacy_ckey = re.sub(r"\s+", " ", f"{status_tag}|{title}|{body}".strip())[:300]
    if ckey in cache:
        entry = cache[ckey]
        return bool(entry.get("is_valid", False)), entry.get("reason")
    if legacy_ckey in cache and (not posted_utc or posted_utc[:10] >= "2026-10-19" or not cache[legacy_ckey].get("is_valid")):
        entry = cache[legacy_ckey]
        return bool(entry.get("is_valid", False)), entry.get("reason")

    post_summary = (
        f"Platform: {platform or 'Unknown'}\n"
        f"Posted UTC: {posted_utc or '2026-10-21'}\n"
        f"Status Tag: {status_tag or 'None'}\n"
        f"Is Comment on ISO Thread: {is_comment}\n"
        f"Title: {title}\n"
        f"Body: {body}"
    )
    llm_res = _call_llm_holistic_single(post_summary)
    if llm_res is not None:
        is_valid, reason = llm_res
        cache[ckey] = {"is_valid": is_valid, "reason": reason, "evaluated_by": "llm"}
        _save_holistic_cache(cache)
        return is_valid, reason

    # Semantic fallback if LLM endpoint is temporarily rate-limited
    lower = full_text.lower().replace("\u00a0", " ")
    title_lower = title.lower().replace("\u00a0", " ")

    if status_tag.upper() in ("SOLD", "PAST") or "[sold]" in lower:
        return False, f"Already marked {status_tag.upper() or 'SOLD'} on platform"

    # Extract comment audit note if present, and strip it from lower text so audit notes don't trigger date matches
    cmt_note = ""
    cmt_match = re.search(r"\[Comments Audit:([^\]]+)\]", full_text, re.IGNORECASE)
    if cmt_match:
        cmt_note = f" ({cmt_match.group(1).strip()})"
    clean_lower = re.sub(r"\[comments audit:[^\]]+\]", "", lower).strip()

    # Check other cities/events
    other_city = re.findall(r"\b(vegas|las\s+vegas|maryland|irwindale|socal|southern\s+california|texas|ohio|carolina|pa\s+ren)\b", lower)
    if other_city and "norcal" not in lower and "northern california" not in lower:
        return False, f"Wrong Renaissance Faire / city ({other_city[0].title()}, not NorCal Ren Faire in Hollister)"

    # Check scam groups, fake "Group Admin Here" posts, discounted-ticket bait, and scammer callouts FIRST so they show as Likely Scams!
    if re.search(r"\b(tickets\s+buy,\s*sell\s*&\s*trade|tickets\s+buy\s+sell|group\s+admin\s+here|contact\s+the\s+admin)\b", clean_lower):
        return False, "Likely Scam: Dedicated 'Tickets Buy, Sell & Trade' / 'GROUP ADMIN HERE' Facebook group (known fake-admin deposit scam)"
    if re.search(r"\b(ticket\s+for\s+only\s+\$30|yhe\s+final\s+weekend)\b", clean_lower):
        return False, "Likely Scam: Suspicious below-face-value ad ('ticket for ONLY $30.00!' with typos for sold-out Oct 24)"
    if re.search(r"\b(scammer|scammed\s+me|mods\s+pls\s+ban)\b", clean_lower):
        return False, "Likely Scam Alert: Confirmed NorCal Ren Faire ticket scammer callout (watch out for this username)"
    if re.search(r"\b(not\s+allowed\s+to\s+sell)\b", clean_lower):
        return False, "General Faire rule notice (Admin reminder, not a ticket seller)"
    if platform.startswith("Google Live Web Search"):
        return False, "Google search index snippet (not a direct seller post)"

    # Check physical costumes / clothing / armor / merchandise (including when keyword-spammed with 'not ticket')
    clothing_or_goods_signals = re.findall(
        r"\b(costumes?|garb|outfits?|dress(?:es)?|skirts?|corsets?|bodices?|boots|shoes|hats?|caps?|"
        r"cloaks?|capes?|boleros?|jackets?|shirts?|pants|vests?|swords?|rapiers?|daggers?|sheaths?|"
        r"wands?|mugs?|tankards?|cups?|baskets?|leather|felt|cotton|seamstress|tailor|cloths?|clothing|"
        r"breastplates?|gauntlets?|armor|armour|helmets?|chainmail|pauldrons?|greaves|shield|"
        r"steel|hema|buhurt|pewter|cane|axes?|knifes?|knives|tool\s+kit|trunk\s+lid|gown)\b",
        lower,
    )
    if clothing_or_goods_signals and ("not ticket" in lower or not re.search(r"\b(admission|general\s+admission|etix|pretix|\d+\s+tickets?\s+for\s+sale)\b", title_lower)):
        sample = ", ".join(sorted(set(clothing_or_goods_signals))[:3])
        return False, f"Selling physical costume / armor / item ({sample}), not event admission"

    # Check post date vs relative date words ('tomorrow', 'today', 'this weekend')
    wrong_dates_found = [tok for tok in WRONG_DATE_TOKENS if tok in clean_lower]
    extra_wrong = re.findall(r"\b(oct\.?\s*(?:10|11|17|18|25)(?:th)?|10-(?:10|11|17|18|25)|sunday\s+the\s+25th|the\s+25th)\b", clean_lower)
    wrong_dates_found.extend(extra_wrong)
    oct24_found = bool(
        any(tok in clean_lower for tok in ("10/24", "10-24", "oct 24", "oct. 24", "october 24", "oct24", "oct 24th", "october 24th"))
        or re.search(r"\b(saturday\s+the\s+24th|sat\s+the\s+24th|the\s+24th)\b", clean_lower)
    )
    if posted_utc and posted_utc[:10] < "2026-10-19" and not oct24_found:
        return False, f"Archived post from {posted_utc[:10]} for a past Faire weekend (not Saturday, Oct 24){cmt_note}"
    if posted_utc and posted_utc[:10] == "2026-10-25" and not oct24_found:
        return False, f"Post from Sunday, Oct 25 for Sunday Faire admission (not Saturday, Oct 24){cmt_note}"
    if wrong_dates_found and not oct24_found:
        return False, f"Wrong Faire date ({wrong_dates_found[0]}) — Not Saturday, October 24{cmt_note}"

    # Check Buyer ISO / Looking to buy / Question post
    buyer_phrases = re.findall(
        r"\b(looking\s+for|looking\s+to\s+buy|iso\b|in\s+search\s+of|wtb\b|want\s+to\s+buy|wanted|"
        r"buying|need\s+\d*\s*tickets?|anyone\s+selling|anyone\s+have\s+(?:an\s+)?extra|"
        r"does\s+anyone\s+have|willing\s+to\s+purchase|save\s+this\s+birthday|didn't\s+grab\s+tickets|"
        r"forgot\s+to\s+get\s+tickets?|shot\s+in\s+the\s+dark)\b",
        lower,
    )
    seller_phrases = re.findall(
        r"\b(selling|i\s+have\s+\d+|i\s+can\s+sell\s+you|have\s+an\s+extra\s+ticket\s+for\s+sale|"
        r"can't\s+make\s+it\s+anymore\s+selling)\b",
        lower,
    )
    if (buyer_phrases or title.strip().endswith("?")) and not seller_phrases and not is_comment:
        return False, f"Buyer 'ISO / Looking to Buy' post (not a seller){cmt_note or ' — 0 seller comments found on this post'}"

    admission_signals = re.findall(
        r"\b(tickets?|tix|wristbands?|general\s+admission|admit\s+one|passes|etix|qr\s*code|parking\s+pass)\b",
        lower,
    )
    if not is_comment and not admission_signals and "i can sell you northern california renaissance faire" not in lower:
        return False, "General Faire discussion or non-ticket post (does not offer event admission for sale)"

    return True, None


def is_merch_or_costume(text: str) -> bool:
    ok, reason = analyze_post_holistically("", text)
    return bool(reason and "physical costume" in reason.lower())


def classify_filtered_reason(
    text: str,
    status_tag: str = "",
    is_comment: bool = False,
    posted_utc: str = "",
    platform: str = "",
) -> str | None:
    parts = text.split("\n", 1)
    t = parts[0]
    b = parts[1] if len(parts) > 1 else ""
    ok, reason = analyze_post_holistically(
        t, b, status_tag=status_tag, is_comment=is_comment, posted_utc=posted_utc, platform=platform
    )
    return None if ok else reason


def load_learned_keywords() -> list[str]:
    if LEARNED_KEYWORDS_FILE.exists():
        try:
            data = json.loads(LEARNED_KEYWORDS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:
            pass
    return []


def get_active_search_terms() -> list[str]:
    learned = load_learned_keywords()
    combined = list(BASE_SEARCH_TERMS)
    for kw in learned:
        if kw.lower() not in [c.lower() for c in combined]:
            combined.append(kw)
    return combined


def learn_keywords_from_listings(listings: list[TicketListing]) -> list[str]:
    """Scan promising posts (scam_score < 60) for new Faire/venue/theme phrases and auto-add them to our search vocabulary."""
    learned = load_learned_keywords()
    existing_lower = {k.lower() for k in BASE_SEARCH_TERMS} | {k.lower() for k in learned}

    candidate_patterns = [
        r"\b(nor\s*cal\s+ren\s*faire?)\b",
        r"\b(renfaire|renfair)\b",
        r"\b(casa\s+de\s+frutas?)\b",
        r"\b(hollister\s+ren\s*faire?)\b",
        r"\b(pacheco\s+pass\s+ren\s*faire?)\b",
        r"\b(halloween\s+fantasy\s+weekend)\b",
        r"\b(ncrf\s*2026|ncrf)\b",
        r"\b(willington\s+shire|willington)\b",
    ]
    newly_added: list[str] = []
    for item in listings:
        # Learn from both promising listings AND real buyer ISO posts (how real humans phrase the event!)
        text = f"{item.title}\n{item.body}"
        for pat in candidate_patterns:
            for match in re.findall(pat, text, re.IGNORECASE):
                term = re.sub(r"\s+", " ", match.strip().lower())
                if len(term) >= 4 and term not in existing_lower:
                    learned.append(term)
                    existing_lower.add(term)
                    newly_added.append(term)

    if newly_added:
        LEARNED_KEYWORDS_FILE.write_text(json.dumps(learned, indent=2), encoding="utf-8")
    return learned


def matches_oct24(text: str) -> bool:
    return classify_filtered_reason(text) is None


def mark_filtered(listing: TicketListing, reason: str) -> TicketListing:
    """Score the listing and mark it as FILTERED OUT / REJECTED with the exact reason."""
    listing = score_listing(listing)
    listing.scam_score = max(listing.scam_score, 85)
    listing.risk_level = f"FILTERED OUT ({reason})"
    listing.red_flags.insert(0, f"Filtered Out Reason: {reason}")
    return listing


def score_listing(listing: TicketListing) -> TicketListing:
    """Compute a 0-100 Scam/Bot Risk Score with detailed red and green flags."""
    is_broker = any(b in listing.platform for b in ("Vivid Seats", "StubHub", "SeatGeek"))
    score = 15 if is_broker else 25
    red_flags: list[str] = []
    green_flags: list[str] = []

    combined_text = f"{listing.title}\n{listing.body}"
    lower_text = combined_text.lower()

    if is_broker:
        green_flags.append(
            f"{listing.platform} includes a 100% buyer refund guarantee if the barcode fails"
        )
        red_flags.append(
            "Note: NorCal Ren Faire uses static Etix PDFs; a broker refund won't save the drive to Hollister if a seller double-sold the PDF"
        )

    for pattern, weight, reason in SCAM_PAYMENT_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            score += weight
            red_flags.append(reason)

    for pattern, weight, reason in SAFE_PAYMENT_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            score += weight
            green_flags.append(reason)

    for pattern, weight, reason in BOT_PHRASE_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            score += weight
            red_flags.append(reason)

    if listing.price_usd is None:
        listing.price_usd = extract_price(combined_text)

    if listing.price_usd is not None:
        is_pair = bool(re.search(r"\b(2\s*tickets|two\s*tickets|pair|set\s*of\s*2)\b", lower_text))
        per_ticket = listing.price_usd / 2.0 if (is_pair and listing.price_usd >= 65) else listing.price_usd

        if per_ticket < 25:
            score += 30
            red_flags.append(
                f"Suspiciously low price (${per_ticket:.0f}/ticket vs. $42 official face value)"
            )
        elif 35 <= per_ticket <= 55:
            score -= 10
            green_flags.append(
                f"Price (${per_ticket:.0f}/ticket) aligns with official $42 face value (+ optional $12 parking)"
            )
        elif per_ticket > 90:
            score += 15
            red_flags.append(
                f"Heavy scalper markup (${per_ticket:.0f}/ticket vs. $42 face value)"
            )

    if re.search(r"\b(plus\s+fees|paid\s+\$[5-9]\d\s+after\s+fees|service\s+fees)\b", lower_text):
        score += 20
        red_flags.append(
            "Claims extra checkout fees (NorCal Ren Faire $42 price is all-inclusive under CA SB-478)"
        )

    seller = listing.seller
    if seller:
        current_year = datetime.now().year
        if seller.joined_year is not None and seller.account_age_days is None:
            seller.account_age_days = max(30, (current_year - seller.joined_year) * 365)

        if seller.account_age_days is not None:
            if seller.account_age_days < 180:
                score += 30
                red_flags.append(
                    f"Recently created profile ({seller.account_age_days} days old / joined {seller.joined_year or 'recently'})"
                )
            elif seller.account_age_days >= 1095:
                score -= 10
                green_flags.append(
                    f"Established profile ({seller.account_age_days // 365}+ years old)"
                )

        total_karma = (seller.post_karma or 0) + (seller.comment_karma or 0)
        if seller.post_karma is not None and total_karma < 30:
            score += 25
            red_flags.append(f"Very low Reddit karma ({total_karma} total karma)")
        elif total_karma >= 500:
            score -= 10
            green_flags.append(f"Active Reddit community karma ({total_karma} total karma)")

        if seller.has_verified_email is False:
            score += 15
            red_flags.append("Unverified email on seller account")

        if seller.recent_ticket_sub_count >= 3:
            score += 35
            red_flags.append(
                f"Account posts across {seller.recent_ticket_sub_count} different ticket/event boards (bot/scalper pattern)"
            )

        if seller.local_bay_area_signals > 0:
            score -= 15
            green_flags.append(
                f"Verified local Bay Area / NorCal profile signals ({seller.local_bay_area_signals} found)"
            )
        elif seller.platform.startswith("Facebook") and seller.local_bay_area_signals == 0:
            score += 15
            red_flags.append("No visible California / Bay Area location on Facebook profile")

        if seller.fb_rating_count is not None and seller.fb_rating_count > 0:
            score -= 10
            green_flags.append(f"Has {seller.fb_rating_count} Facebook Marketplace rating(s)")

        if seller.is_vouched is True:
            score -= 15
            green_flags.append("Seller holds 'Vouched' community reputation status on VouchFirst")
        elif seller.is_vouched is False:
            score += 15
            red_flags.append("Seller is marked 'Not vouched' on VouchFirst")

        if seller.multi_date_duplicate_posts >= 3:
            score += 25
            red_flags.append(
                f"Seller posted identical ticket listings across {seller.multi_date_duplicate_posts} different Faire dates (commercial reseller/bot pattern)"
            )

    listing.scam_score = max(0, min(100, score))
    if listing.scam_score >= 60:
        listing.risk_level = "HIGH (Likely Scam/Bot)"
    elif listing.scam_score >= 35:
        listing.risk_level = "MEDIUM (Verify via Screen Recording + PayPal G&S)"
    else:
        listing.risk_level = "LOW (Promising — Still Use PayPal G&S)"

    listing.red_flags = red_flags
    listing.green_flags = green_flags
    return listing


# ---------------------------------------------------------------------------
# 2. Fast HTTP Scrapers (Etix, VouchFirst, Craigslist, Reddit, Broker JSON-LD)
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check_official_etix() -> list[TicketListing]:
    """Check if returned/released tickets appear on the official tickets.norcalrenfaire.com (Pretix) or Etix page."""
    listings: list[TicketListing] = []
    try:
        pretix_page = http_get(PRETIX_URL)
        lower_p = pretix_page.lower()
        if ("october 24" in lower_p or "oct 24" in lower_p) and ("available" in lower_p or "add to cart" in lower_p or "buy" in lower_p) and "sold out" not in lower_p:
            listings.append(
                TicketListing(
                    id="pretix-official-oct24",
                    platform="Official Pretix Portal (tickets.norcalrenfaire.com)",
                    title="OFFICIAL TICKET DROP DETECTED — Northern California Renaissance Faire",
                    url=PRETIX_URL,
                    body="Official tickets.norcalrenfaire.com/PFP/NCRF2026/ portal shows availability for Oct 24!",
                    posted_utc=datetime.now(timezone.utc).isoformat(),
                    price_usd=OFFICIAL_ADULT_GA_PRICE_USD,
                    scam_score=0,
                    risk_level="OFFICIAL (100% Authentic)",
                    green_flags=["Official 2026 Northern California Renaissance Faire Pretix portal"],
                )
            )
    except Exception as exc:
        print(f"[warn] Official Pretix check failed: {exc}", file=sys.stderr)
    try:
        page = http_get(ETIX_URL)
        if "No Tickets Available" not in page and ("October 24" in page or "10/24" in page):
            listings.append(
                TicketListing(
                    id="etix-official-oct24",
                    platform="Official Etix",
                    title="OFFICIAL TICKET DROP DETECTED — Northern California Renaissance Faire",
                    url=ETIX_URL,
                    body="Official Etix venue page no longer says 'No Tickets Available'. Check immediately!",
                    posted_utc=datetime.now(timezone.utc).isoformat(),
                    price_usd=OFFICIAL_ADULT_GA_PRICE_USD,
                    scam_score=0,
                    risk_level="OFFICIAL (100% Authentic)",
                    green_flags=["Official Northern California Renaissance Faire ticketing partner"],
                )
            )
    except Exception as exc:
        print(f"[warn] Etix check failed: {exc}", file=sys.stderr)
    return listings


def scrape_vouchfirst() -> list[TicketListing]:
    """Scrape VouchFirst Northern California Renaissance Faire fan-to-fan listings."""
    listings: list[TicketListing] = []
    try:
        raw_html = http_get(VOUCHFIRST_URL)
        text = html.unescape(re.sub(r"<[^>]+>", "\n", raw_html))
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        seller_counts: dict[str, int] = {}
        for i, ln in enumerate(lines):
            if ln == "Selling" and i + 2 < len(lines):
                seller_line = lines[i + 2]
                uname = seller_line.split("·")[0].strip()
                seller_counts[uname] = seller_counts.get(uname, 0) + 1

        in_oct24_section = False
        for i, ln in enumerate(lines):
            if ln in ("OCT17", "OCT18", "OCT25"):
                in_oct24_section = False
            elif ln == "OCT24":
                in_oct24_section = True
            elif ln == "OCT" and i + 1 < len(lines):
                if lines[i + 1] == "24":
                    in_oct24_section = True
                elif lines[i + 1] in ("17", "18", "25"):
                    in_oct24_section = False

            if in_oct24_section and ln == "Selling" and i + 2 < len(lines):
                title = lines[i + 1]
                seller_line = lines[i + 2]
                uname = seller_line.split("·")[0].strip()
                is_not_vouched = "not vouched" in uname.lower()

                seller = SellerProfile(
                    platform="VouchFirst",
                    username=uname,
                    is_vouched=not is_not_vouched,
                    multi_date_duplicate_posts=seller_counts.get(uname, 1),
                    profile_url=f"https://www.vouchfirst.com/u/{urllib.parse.quote(uname)}" if not is_not_vouched else VOUCHFIRST_URL,
                )
                listing = TicketListing(
                    id=f"vf-oct24-{uname}-{title[:25]}",
                    platform="VouchFirst (Oct 24 - SELLING)",
                    title=f"[SELLING] {title}",
                    url=VOUCHFIRST_URL,
                    body=f"Seller: {seller_line}",
                    posted_utc=datetime.now(timezone.utc).isoformat(),
                    price_usd=extract_price(title),
                    seller=seller,
                )
                listings.append(score_listing(listing))
    except Exception as exc:
        print(f"[warn] VouchFirst check failed: {exc}", file=sys.stderr)
    return listings


def scrape_craigslist() -> list[TicketListing]:
    """Fetch SF Bay Area, Monterey/Hollister, and Sacramento Craigslist ticket listings."""
    regions = ["sfbay", "monterey", "sacramento"]
    queries = ["renaissance faire", "ren faire", "norcal ren"]
    discovered: dict[str, TicketListing] = {}

    for region in regions:
        for q in queries:
            encoded_q = urllib.parse.quote_plus(q)
            search_url = f"https://{region}.craigslist.org/search/sss?query={encoded_q}&sort=date&format=rss"
            try:
                xml_text = http_get(search_url)
                root = ET.fromstring(xml_text)
                for item in root.findall(".//{*}item"):
                    title = html.unescape((item.findtext("{*}title") or "").strip())
                    link = (item.findtext("{*}link") or "").strip()
                    desc_raw = (item.findtext("{*}description") or "").strip()
                    desc = html.unescape(re.sub(r"<[^>]+>", " ", desc_raw))
                    date_str = (item.findtext("{*}date") or datetime.now(timezone.utc).isoformat()).strip()

                    if not link or link in discovered:
                        continue
                    if not matches_oct24(f"{title} {desc}"):
                        continue
                    if re.search(r"\b(iso|looking\s+for|wtb|wanted|buying)\b", title.lower()):
                        continue

                    listing = TicketListing(
                        id=f"cl-{stable_id_hash(link)}",
                        platform=f"Craigslist ({region})",
                        title=title,
                        url=link,
                        body=desc,
                        posted_utc=date_str,
                        price_usd=extract_price(title) or extract_price(desc),
                    )
                    discovered[link] = score_listing(listing)
            except Exception:
                continue
    return list(discovered.values())


def fetch_reddit_seller_profile(username: str) -> SellerProfile:
    """Audit a Reddit user's Bay Area history vs. multi-subreddit ticket-resale activity via PullPush API."""
    profile = SellerProfile(
        platform="Reddit",
        username=username,
        profile_url=f"https://www.reddit.com/user/{username}",
    )
    if not username or username in ("[deleted]", "AutoModerator"):
        return profile

    try:
        q_user = urllib.parse.quote(username)
        raw = http_get(f"https://api.pullpush.io/reddit/search/comment/?author={q_user}&size=25", timeout=10)
        items = json.loads(raw).get("data", [])
        ticket_subs: set[str] = set()
        bay_area_subs = {
            "bayarea", "sanjose", "sanfrancisco", "oakland", "berkeley",
            "santacruz", "montereybay", "norcal", "renfaire", "sacramento", "mountainview",
            "sunnyvale", "paloalto", "fresno", "modesto", "stockton",
        }
        oldest_ts = None
        for item in items:
            sub = str(item.get("subreddit", "")).lower()
            if sub in bay_area_subs:
                profile.local_bay_area_signals += 1
            if any(k in sub for k in ("ticket", "resale", "aves", "concert", "stubhub")):
                ticket_subs.add(sub)
            ts = item.get("created_utc")
            if ts and (oldest_ts is None or float(ts) < oldest_ts):
                oldest_ts = float(ts)
        profile.recent_ticket_sub_count = len(ticket_subs)
    except Exception:
        pass
    return profile


def scrape_reddit() -> list[TicketListing]:
    """Search Reddit submissions & comments via PullPush API (HTTP 200, avoids Reddit 403 block)."""
    listings: dict[str, TicketListing] = {}
    queries = [
        ("submission", "https://api.pullpush.io/reddit/search/submission/?q=renaissance+faire+ticket&sort=desc&size=25"),
        ("submission", "https://api.pullpush.io/reddit/search/submission/?q=renaissance+fair+ticket&sort=desc&size=25"),
        ("submission", "https://api.pullpush.io/reddit/search/submission/?q=%22casa+de+fruta%22+ticket&sort=desc&size=25"),
        ("submission", "https://api.pullpush.io/reddit/search/submission/?q=%22ren+fair%22+ticket&sort=desc&size=25"),
        ("comment", "https://api.pullpush.io/reddit/search/comment/?q=renaissance+faire+ticket&sort=desc&size=25"),
        ("comment", "https://api.pullpush.io/reddit/search/comment/?q=norcal+ren+faire&sort=desc&size=25"),
        ("comment", "https://api.pullpush.io/reddit/search/comment/?q=norcal+ren+fair&sort=desc&size=25"),
        ("comment", "https://api.pullpush.io/reddit/search/comment/?q=%22casa+de+fruta%22&sort=desc&size=25"),
    ]
    for learned_kw in load_learned_keywords()[:4]:
        q_enc = urllib.parse.quote_plus(f'"{learned_kw}" ticket')
        queries.append(("submission", f"https://api.pullpush.io/reddit/search/submission/?q={q_enc}&sort=desc&size=15"))
        queries.append(("comment", f"https://api.pullpush.io/reddit/search/comment/?q={q_enc}&sort=desc&size=15"))
    target_subs = {
        "tickets", "ticketresale", "sanjose", "bayarea", "renfaire", "norcal",
        "mountainview", "sacramento", "santacruz", "montereybay", "sanfrancisco",
        "oakland", "fresno", "modesto", "stockton", "sunnyvale", "paloalto",
    }
    for kind, url in queries:
        try:
            raw = http_get(url, timeout=15)
            items = json.loads(raw).get("data", [])
            for pdata in items:
                sub = str(pdata.get("subreddit", "")).lower()
                if sub not in target_subs and "norcal" not in str(pdata.get("body", "") + pdata.get("title", "")).lower():
                    continue
                item_id = str(pdata.get("id", ""))
                author = str(pdata.get("author", ""))
                created_utc = float(pdata.get("created_utc", time.time()))
                # Only look at posts/comments from the last 14 days
                if time.time() - created_utc > 14 * 86400:
                    continue
                if not item_id or author in ("[deleted]", "AutoModerator"):
                    continue

                if kind == "submission":
                    title = str(pdata.get("title", ""))
                    selftext = str(pdata.get("selftext", ""))
                    num_comments = int(pdata.get("num_comments", 0) or 0)
                    posted_iso = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
                    permalink = f"https://www.reddit.com{pdata.get('permalink', f'/r/{sub}/comments/{item_id}/')}"

                    cmt_audit_note = f"[Comments Audit: {num_comments} comments on this Reddit post — no sellers replied]"
                    if num_comments > 0 and posted_iso[:10] >= "2026-10-18":
                        try:
                            c_raw = http_get(f"https://api.pullpush.io/reddit/search/comment/?link_id={item_id}", timeout=10)
                            c_items = [
                                c for c in json.loads(c_raw).get("data", [])
                                if c.get("author") not in (None, "[deleted]", "AutoModerator", author)
                            ]
                            if not c_items:
                                cmt_audit_note = "[Comments Audit: 0 comments from other users on this post]"
                            else:
                                c_summaries: list[str] = []
                                for cdata in c_items:
                                    c_id = str(cdata.get("id", ""))
                                    c_auth = str(cdata.get("author", ""))
                                    c_txt = str(cdata.get("body", "")).strip()
                                    c_reason = classify_filtered_reason(c_txt, is_comment=True, posted_utc=posted_iso, platform=f"Reddit Comment (r/{sub})")
                                    c_status = "Possible Seller! (Added as card)" if not c_reason else f"Not selling ({c_reason})"
                                    c_summaries.append(f"u/{c_auth}: \"{c_txt[:45]}\" -> {c_status}")
                                    if not c_reason and c_id:
                                        c_listing = TicketListing(
                                            id=f"reddit-cmt-{c_id}",
                                            platform=f"Reddit Comment on ISO (r/{sub})",
                                            title=f"Comment by u/{c_auth} on '{title[:40]}': {c_txt[:50]}",
                                            url=permalink,
                                            body=f"Replying to post '{title}':\n{c_txt[:450]}",
                                            posted_utc=posted_iso,
                                            price_usd=extract_price(c_txt),
                                            seller=fetch_reddit_seller_profile(c_auth),
                                        )
                                        listings[f"cmt-{c_id}"] = score_listing(c_listing)
                                cmt_audit_note = f"[Comments Audit: {len(c_items)} comment(s) evaluated — " + "; ".join(c_summaries[:3]) + "]"
                        except Exception:
                            cmt_audit_note = f"[Comments Audit: {num_comments} comment(s) listed on Reddit]"

                    body_with_audit = f"{selftext[:420]}\n{cmt_audit_note}".strip()
                    combined = f"{title}\n{body_with_audit}"
                    reason = classify_filtered_reason(combined, posted_utc=posted_iso, platform=f"Reddit (r/{pdata.get('subreddit', sub)})")
                    r_seller = SellerProfile(platform="Reddit", username=author, profile_url=f"https://www.reddit.com/user/{author}") if reason else fetch_reddit_seller_profile(author)
                    listing = TicketListing(
                        id=f"reddit-post-{item_id}",
                        platform=f"Reddit (r/{pdata.get('subreddit', sub)})",
                        title=title[:90],
                        url=permalink,
                        body=body_with_audit,
                        posted_utc=posted_iso,
                        price_usd=extract_price(combined),
                        seller=r_seller,
                    )
                    listings[f"post-{item_id}"] = mark_filtered(listing, reason) if reason else score_listing(listing)
                else:
                    c_body = str(pdata.get("body", ""))
                    if not c_body:
                        continue
                    posted_iso = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
                    reason = classify_filtered_reason(c_body, is_comment=True, posted_utc=posted_iso, platform=f"Reddit Comment (r/{pdata.get('subreddit', sub)})")
                    permalink = f"https://www.reddit.com{pdata.get('permalink', '')}"
                    r_seller = SellerProfile(platform="Reddit", username=author, profile_url=f"https://www.reddit.com/user/{author}") if reason else fetch_reddit_seller_profile(author)
                    listing = TicketListing(
                        id=f"reddit-cmt-{item_id}",
                        platform=f"Reddit Comment (r/{pdata.get('subreddit', sub)})",
                        title=f"Comment by u/{author}: {c_body.splitlines()[0][:70]}",
                        url=permalink if permalink != "https://www.reddit.com" else f"https://www.reddit.com/r/{sub}/",
                        body=c_body[:500],
                        posted_utc=posted_iso,
                        price_usd=extract_price(c_body),
                        seller=r_seller,
                    )
                    listings[f"cmt-{item_id}"] = mark_filtered(listing, reason) if reason else score_listing(listing)
        except Exception:
            continue
    return list(listings.values())


def scrape_resale_brokers_http() -> list[TicketListing]:
    """Attempt lightweight JSON-LD Offer extraction from Vivid Seats, StubHub, and SeatGeek."""
    brokers = [
        ("Vivid Seats", VIVID_SEATS_URL),
        ("StubHub", STUBHUB_URL),
        ("SeatGeek", SEATGEEK_URL),
    ]
    results: list[TicketListing] = []
    for name, url in brokers:
        try:
            page = http_get(url)
            ld_blocks = re.findall(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                page,
                re.DOTALL | re.IGNORECASE,
            )
            for block in ld_blocks:
                try:
                    data = json.loads(block.strip())
                except Exception:
                    continue
                events = data if isinstance(data, list) else [data]
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    start_date = str(ev.get("startDate", ""))
                    ev_name = str(ev.get("name", ""))
                    if "2026-10-24" not in start_date and "10/24" not in ev_name:
                        continue
                    offers = ev.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    low_price = offers.get("lowPrice") or offers.get("price")
                    avail = str(offers.get("availability", ""))
                    if low_price or "InStock" in avail:
                        price_val = float(low_price) if low_price else None
                        listing = TicketListing(
                            id=f"broker-{name.lower().replace(' ', '')}-oct24-{price_val}",
                            platform=name,
                            title=f"{ev_name or 'Northern California Renaissance Faire'} (Sat Oct 24)",
                            url=str(ev.get("url") or url),
                            body=f"Live resale inventory detected on {name} for Oct 24, 2026.",
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=price_val,
                        )
                        results.append(score_listing(listing))
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# 3. Playwright Browser Scraper (Facebook Marketplace, Vetted FB Groups, Brokers)
# ---------------------------------------------------------------------------

def audit_facebook_seller_profile(context: Any, profile_url: str) -> SellerProfile:
    """Open a temporary background tab to inspect a Facebook seller's profile without disrupting the main feed page."""
    seller = SellerProfile(
        platform="Facebook",
        username=profile_url.rstrip("/").split("/")[-1][:40],
        profile_url=profile_url,
    )
    prof_page = None
    try:
        prof_page = context.new_page()
        prof_page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        prof_page.wait_for_timeout(2000)
        body_text = prof_page.locator("body").inner_text()

        join_match = re.search(r"Joined(?:\s+Facebook)?\s+in\s+(20\d{2}|19\d{2})", body_text, re.IGNORECASE)
        if join_match:
            seller.joined_year = int(join_match.group(1))
        elif re.search(r"Joined\s+(?:last\s+month|this\s+week|\d+\s+days?\s+ago)", body_text, re.IGNORECASE):
            seller.account_age_days = 15

        bay_area_cities = (
            "san francisco", "san jose", "oakland", "berkeley", "hollister",
            "gilroy", "morgan hill", "santa cruz", "salinas", "monterey",
            "palo alto", "sunnyvale", "santa clara", "fremont", "sacramento", "california",
        )
        lower_body = body_text.lower()
        seller.local_bay_area_signals = sum(1 for city in bay_area_cities if city in lower_body)

        rating_match = re.search(r"(\d+)\s+ratings?", body_text, re.IGNORECASE)
        if rating_match:
            seller.fb_rating_count = int(rating_match.group(1))
    except Exception:
        pass
    finally:
        if prof_page is not None:
            try:
                prof_page.close()
            except Exception:
                pass
    return seller


def scrape_with_playwright(profile_dir: Path, headless: bool = False) -> list[TicketListing]:
    """Use a persistent Chromium context to check Brokers, FB Marketplace, and Vetted FB Groups."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[error] Playwright is not installed. Run in your terminal:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return []

    discovered: list[TicketListing] = []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        # --- A0. Check VouchFirst, Craigslist & Old.Reddit via Playwright ---
        try:
            page.goto(VOUCHFIRST_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2500)
            vf_text = page.locator("body").inner_text()
            vf_lines = [ln.strip() for ln in vf_text.splitlines() if ln.strip()]

            seller_counts: dict[str, int] = {}
            for i, ln in enumerate(vf_lines):
                if ln.upper() in ("SELLING", "SOLD") and i + 2 < len(vf_lines):
                    uname = vf_lines[i + 2].split("·")[0].strip()
                    seller_counts[uname] = seller_counts.get(uname, 0) + 1

            in_oct24 = False
            for i, ln in enumerate(vf_lines):
                if ln == "OCT" and i + 1 < len(vf_lines):
                    if vf_lines[i + 1] == "24":
                        in_oct24 = True
                    elif vf_lines[i + 1] in ("25", "17", "18", "10", "11"):
                        in_oct24 = False
                if in_oct24 and ln.upper() in ("SELLING", "SOLD") and i + 2 < len(vf_lines):
                    status_tag = ln.upper()
                    title = vf_lines[i + 1]
                    if title.upper() == "PAST" and i + 3 < len(vf_lines):
                        status_tag = "PAST"
                        title = vf_lines[i + 2]
                        seller_line = vf_lines[i + 3]
                    else:
                        seller_line = vf_lines[i + 2]
                    uname = seller_line.split("·")[0].strip()
                    age_hint = vf_lines[i + 4] if (i + 4 < len(vf_lines) and "ago" in vf_lines[i + 4]) else ""
                    is_not_vouched = "not vouched" in uname.lower()
                    dup_count = seller_counts.get(uname, 1)
                    seller = SellerProfile(
                        platform="VouchFirst",
                        username=uname,
                        is_vouched=not is_not_vouched,
                        multi_date_duplicate_posts=dup_count,
                        profile_url=f"https://www.vouchfirst.com/u/{urllib.parse.quote(uname)}" if not is_not_vouched else VOUCHFIRST_URL,
                    )
                    listing = TicketListing(
                        id=f"vf-oct24-{uname}-{title[:25]}",
                        platform=f"VouchFirst (Oct 24 - {status_tag})",
                        title=f"[{status_tag}] {title}",
                        url=VOUCHFIRST_URL,
                        body=f"Seller: {seller_line} {age_hint} (Seller appears on {dup_count} date section(s) on VouchFirst)",
                        posted_utc=datetime.now(timezone.utc).isoformat(),
                        price_usd=extract_price(title),
                        seller=seller,
                    )
                    if status_tag in ("SOLD", "PAST"):
                        discovered.append(mark_filtered(listing, f"VouchFirst listing is already marked {status_tag}"))
                    else:
                        discovered.append(score_listing(listing))
            update_dashboard(discovered, datetime.now().strftime("%I:%M:%S %p") + " (Scanning Craigslist...)")

        except Exception as exc:
            print(f"[warn] Playwright VouchFirst check skipped: {exc}", file=sys.stderr)

        seen_cl_urls: set[str] = set()
        for cl_region in ("sfbay", "monterey", "sacramento", "stockton", "modesto", "fresno", "merced", "slo", "chico"):
            try:
                cl_query_expr = urllib.parse.quote_plus('"renaissance faire"|"ren faire"|"renaissance fair"|"ren fair"|"casa de fruta"')
                cl_url = f"https://{cl_region}.craigslist.org/search/sss?query={cl_query_expr}#search=1~newest~0~0"
                page.goto(cl_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                cl_cards = page.locator("li.cl-search-result, div.cl-search-result").all()
                cl_links: list[tuple[str, str]] = []
                for card in cl_cards[:6]:
                    link_el = card.locator("a.posting-title, a[href*='.html']").first
                    if link_el.count() == 0:
                        continue
                    href = link_el.get_attribute("href") or ""
                    card_title = link_el.inner_text().strip() or card.inner_text().strip()
                    if href and href not in seen_cl_urls and href not in [u for u, _ in cl_links]:
                        cl_links.append((href, card_title))
                        seen_cl_urls.add(href)

                for href, card_title in cl_links:
                    try:
                        page.goto(href, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1000)
                        title_el = page.locator("#titletextonly, h1.postingtitle").first
                        full_title = title_el.inner_text().strip() if title_el.count() > 0 else card_title
                        body_el = page.locator("#postingbody").first
                        full_body = body_el.inner_text().replace("QR Code Link to This Post", "").strip() if body_el.count() > 0 else page.locator("body").inner_text()[:600]
                        combined_cl = f"{full_title}\n{full_body}"
                        reason = classify_filtered_reason(combined_cl, platform=f"Craigslist ({cl_region})")
                        listing = TicketListing(
                            id=f"cl-pw-{href.rstrip('/').split('/')[-1][:35]}",
                            platform=f"Craigslist ({cl_region})",
                            title=full_title[:90],
                            url=href,
                            body=full_body[:500],
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=extract_price(combined_cl),
                        )
                        discovered.append(mark_filtered(listing, reason) if reason else score_listing(listing))
                    except Exception:
                        continue
                update_dashboard(discovered, datetime.now().strftime("%I:%M:%S %p") + f" (Scanned Craigslist {cl_region}...)")
            except Exception as exc:
                print(f"[warn] Craigslist ({cl_region}) check skipped: {exc}", file=sys.stderr)

        # --- A0b. Check Google Search ("Past 24 Hours" Web Discovery), Nextdoor, CashorTrade, Tixel ---
        extra_marketplaces = [
            ("Google Live Web Search (Past 24h)", "https://www.google.com/search?q=(%22Northern+California+Renaissance+Faire%22+OR+%22NorCal+Ren+Faire%22+OR+%22NorCal+Ren+Fair%22+OR+%22Casa+de+Fruta%22)+%22ticket%22+%2224%22&tbs=qdr:d"),
            ("Nextdoor (For Sale & Free - Faire)", "https://nextdoor.com/for_sale_and_free/?query=renaissance%20faire"),
            ("Nextdoor (For Sale & Free - Fair/Casa de Fruta)", "https://nextdoor.com/for_sale_and_free/?query=casa%20de%20fruta%20tickets"),
            ("Nextdoor (Neighborhood Posts - Faire)", "https://nextdoor.com/news_feed/?query=renaissance%20faire%20ticket"),
            ("Nextdoor (Neighborhood Posts - Fair)", "https://nextdoor.com/news_feed/?query=ren%20fair%20ticket"),
            ("CashorTrade", "https://cashortrade.org/"),
            ("Tixel", "https://tixel.com/us/"),
        ]
        for m_name, m_url in extra_marketplaces:
            try:
                page.goto(m_url, wait_until="domcontentloaded", timeout=18000)
                page.wait_for_timeout(3000)
                if "nextdoor" in m_url:
                    for _ in range(2):
                        page.mouse.wheel(0, 1000)
                        page.wait_for_timeout(1000)
                m_text = page.locator("body").inner_text()
                for m_line in m_text.splitlines():
                    if len(m_line.strip()) > 12 and ("renaissance" in m_line.lower() or "ren faire" in m_line.lower() or "norcal" in m_line.lower()):
                        reason = classify_filtered_reason(m_line, platform=m_name)
                        listing = TicketListing(
                            id=f"extra-{m_name.split()[0].lower()}-{m_line.strip()[:35]}",
                            platform=m_name,
                            title=f"{m_name}: {m_line.strip()[:80]}",
                            url=m_url,
                            body=m_line.strip()[:400],
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=extract_price(m_line),
                        )
                        discovered.append(mark_filtered(listing, reason) if reason else score_listing(listing))
                update_dashboard(discovered, datetime.now().strftime("%I:%M:%S %p") + f" (Scanned {m_name}...)")
            except Exception as exc:
                print(f"[warn] {m_name} check skipped: {exc}", file=sys.stderr)

        # --- A. Check Vivid Seats, StubHub, SeatGeek ---
        broker_targets = [
            ("Vivid Seats", VIVID_SEATS_URL),
            ("StubHub", STUBHUB_URL),
            ("SeatGeek", SEATGEEK_URL),
        ]
        for broker_name, broker_url in broker_targets:
            try:
                page.goto(broker_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                text = page.locator("body").inner_text()
                for line in text.splitlines():
                    if any(tok in line.lower() for tok in ("oct 24", "10/24", "october 24")):
                        price = extract_price(line)
                        listing = TicketListing(
                            id=f"pw-broker-{broker_name}-{stable_id_hash(line)}",
                            platform=broker_name,
                            title=f"{broker_name} Oct 24 Listing: {line[:80]}",
                            url=broker_url,
                            body=line,
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=price,
                        )
                        discovered.append(score_listing(listing))
            except Exception as exc:
                print(f"[warn] Browser check for {broker_name} skipped: {exc}", file=sys.stderr)

        # --- B. Check Facebook Marketplace (SF, San Jose/Hollister, Sacramento) ---
        for fb_mp_label, fb_mp_url in FB_MARKETPLACE_URLS:
            try:
                page.goto(fb_mp_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                if "login" in page.url.lower() or page.locator('input[name="email"], input[name="pass"]').count() > 0:
                    print(
                        "\n[ACTION REQUIRED] Please log into Facebook in the opened Chrome window! "
                        "Waiting 90 seconds so your session can be saved to .antigravity_chrome_profile...\n",
                        file=sys.stderr,
                    )
                    page.wait_for_timeout(90000)

                cards = page.locator('a[href*="/marketplace/item/"]').all()
                item_urls: list[str] = []
                for card in cards[:8]:
                    href = card.get_attribute("href")
                    if href:
                        full_url = f"https://www.facebook.com{href}" if href.startswith("/") else href
                        clean_url = full_url.split("?")[0]
                        if clean_url not in item_urls:
                            item_urls.append(clean_url)

                for item_url in item_urls:
                    try:
                        page.goto(item_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2000)
                        item_text = page.locator("body").inner_text()
                        reason = classify_filtered_reason(item_text)

                        seller_links = page.locator('a[href*="/marketplace/profile/"]').all()
                        seller_profile = None
                        if seller_links and not reason:
                            s_href = seller_links[0].get_attribute("href") or ""
                            s_url = f"https://www.facebook.com{s_href}" if s_href.startswith("/") else s_href
                            seller_profile = audit_facebook_seller_profile(context, s_url.split("?")[0])

                        lines = [ln.strip() for ln in item_text.splitlines() if ln.strip()]
                        title_line = next(
                            (ln for ln in lines if "ren" in ln.lower() or "ticket" in ln.lower() or "faire" in ln.lower()),
                            "Facebook Marketplace Ren Faire Post",
                        )
                        listing = TicketListing(
                            id=f"fb-mp-{clean_url.split('/')[-2] if '/' in clean_url else stable_id_hash(item_url)}",
                            platform=fb_mp_label,
                            title=title_line[:90],
                            url=item_url,
                            body=item_text[:600],
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=extract_price(item_text),
                            seller=seller_profile,
                        )
                        discovered.append(mark_filtered(listing, reason) if reason else score_listing(listing))
                    except Exception:
                        continue
                update_dashboard(discovered, datetime.now().strftime("%I:%M:%S %p") + f" (Scanned {fb_mp_label}...)")
            except Exception as exc:
                print(f"[warn] {fb_mp_label} check skipped: {exc}", file=sys.stderr)

        # --- C. Check All 5 Vetted Facebook Community Groups (Posts + Comments on ISO Posts) ---
        for group_label, group_url in FB_GROUP_URLS:
            try:
                page.goto(group_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                # Scroll down to trigger Facebook feed lazy-loading
                for _ in range(3):
                    page.mouse.wheel(0, 1200)
                    page.wait_for_timeout(1200)

                # Expand "View more comments" / "comments" buttons if visible so we see replies on ISO posts
                try:
                    more_btns = page.locator('span:has-text("View more comments"), span:has-text("more comment")').all()
                    for btn in more_btns[:6]:
                        btn.click(timeout=1200)
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                articles = page.locator('div[role="article"]').all()
                for idx, article in enumerate(articles[:18]):
                    aria_lbl = (article.get_attribute("aria-label") or "").lower()
                    if aria_lbl.startswith("comment by") or aria_lbl.startswith("reply by"):
                        continue  # Handled inside its parent post's comment_nodes loop
                    post_text = article.inner_text().strip()
                    if not post_text or len(post_text) < 20:
                        continue
                    if not any(k in post_text.lower() for k in ("ticket", "tix", "oct", "10/24", "ren", "faire", "pass", "saturday")):
                        continue

                    # Always inspect nested comments under any Faire/ticket group post (ISO posts, megathreads, etc.)
                    comment_nodes = article.locator('div[role="article"]').all()
                    cmt_summaries: list[str] = []
                    parent_only_text = post_text
                    for c_idx, c_node in enumerate(comment_nodes):
                        c_text = c_node.inner_text().strip()
                        if not c_text:
                            continue
                        parent_only_text = parent_only_text.replace(c_text, "").strip()
                        c_links = c_node.locator('a[href*="/user/"], a[href*="facebook.com/"]').all()
                        c_seller = None
                        c_author = "FB User"
                        if c_links:
                            chref = c_links[0].get_attribute("href") or ""
                            curl = f"https://www.facebook.com{chref}" if chref.startswith("/") else chref
                            c_author = curl.rstrip("/").split("/")[-1][:35]
                            c_seller = SellerProfile(platform="Facebook", username=c_author, profile_url=curl.split("?")[0])
                        c_first = next((ln.strip() for ln in c_text.splitlines() if len(ln.strip()) > 3), "FB Comment")
                        c_reason = classify_filtered_reason(c_text, is_comment=True, platform=f"{group_label} (Comment)")
                        if not c_reason and c_seller and c_seller.profile_url:
                            c_seller = audit_facebook_seller_profile(context, c_seller.profile_url)
                        cmt_summaries.append(f"{c_author}: \"{c_first[:40]}\" -> {'Seller (Added as card)' if not c_reason else c_reason}")
                        c_listing = TicketListing(
                            id=f"fb-iso-cmt-{group_label[:15]}-{c_first[:30]}",
                            platform=f"{group_label} (Comment)",
                            title=f"Comment on FB post: {c_first[:75]}",
                            url=group_url,
                            body=f"Comment on FB Group Post:\n{c_text[:500]}",
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=extract_price(c_text),
                            seller=c_seller,
                        )
                        discovered.append(mark_filtered(c_listing, c_reason) if c_reason else score_listing(c_listing))

                    post_text = parent_only_text or post_text
                    is_iso = bool(re.search(
                        r"\b(looking\s+for|looking\s+to\s+buy|iso|need\s+\d?\s*ticket|forgot\s+to\s+get\s+ticket|didn't\s+get\s+a\s+ticket|didn't\s+grab\s+tickets|anyone\s+not\s+going)\b",
                        post_text.lower(),
                    ))

                    if not cmt_summaries:
                        cmt_audit_str = "[Comments Audit: 0 comments on this post so far]"
                    else:
                        cmt_audit_str = f"[Comments Audit: {len(cmt_summaries)} comment(s) evaluated — " + "; ".join(cmt_summaries[:3]) + "]"

                    if is_iso:
                        first_line = next((ln.strip() for ln in post_text.splitlines() if len(ln.strip()) > 10), "FB Group ISO Post")
                        iso_body = f"{post_text[:420]}\n{cmt_audit_str}"
                        reason = classify_filtered_reason(f"{first_line}\n{iso_body}", platform=group_label)
                        iso_listing = TicketListing(
                            id=f"fb-grp-iso-{group_label[:12]}-{first_line[:30]}",
                            platform=group_label,
                            title=f"[ISO Buyer Post] {first_line[:75]}",
                            url=group_url,
                            body=iso_body,
                            posted_utc=datetime.now(timezone.utc).isoformat(),
                            price_usd=extract_price(post_text),
                        )
                        discovered.append(mark_filtered(iso_listing, reason or f"Irrelevant: Buyer ISO post {cmt_audit_str}"))
                        continue

                    post_body_with_audit = f"{post_text[:480]}\n{cmt_audit_str}"
                    reason = classify_filtered_reason(post_body_with_audit, platform=group_label)

                    user_links = article.locator('a[href*="/user/"], a[href*="facebook.com/profile.php"]').all()
                    seller_profile = None
                    if user_links and not reason:
                        u_href = user_links[0].get_attribute("href") or ""
                        u_url = f"https://www.facebook.com{u_href}" if u_href.startswith("/") else u_href
                        seller_profile = audit_facebook_seller_profile(context, u_url.split("?")[0])

                    first_line = next((ln.strip() for ln in post_text.splitlines() if len(ln.strip()) > 10), "FB Group Post")
                    listing = TicketListing(
                        id=f"fb-grp-{group_label[:12]}-{first_line[:35]}",
                        platform=group_label,
                        title=first_line[:90],
                        url=group_url,
                        body=post_body_with_audit,
                        posted_utc=datetime.now(timezone.utc).isoformat(),
                        price_usd=extract_price(post_text),
                        seller=seller_profile,
                    )
                    discovered.append(mark_filtered(listing, reason) if reason else score_listing(listing))
                update_dashboard(discovered, datetime.now().strftime("%I:%M:%S %p") + f" (Scanned {group_label}...)")
            except Exception as exc:
                print(f"[warn] {group_label} check skipped: {exc}", file=sys.stderr)

        context.close()
    return discovered


# ---------------------------------------------------------------------------
# 4. Desktop Notifications & CLI Auditor
# ---------------------------------------------------------------------------

def send_desktop_alert(listing: TicketListing) -> None:
    """Trigger a native macOS / Linux / Windows desktop banner and magical chime for promising tickets."""
    if listing.scam_score >= 60:
        return  # Do not chime for high-risk likely bots/scams

    title = f"Ren Faire Ticket ({listing.platform}) — Risk: {listing.scam_score}/100"
    msg = f"{listing.title} ({f'${listing.price_usd:.0f}' if listing.price_usd else 'Check price'})"

    os_name = platform.system()
    try:
        if os_name == "Darwin":
            safe_title = title.replace('"', "'")
            safe_msg = msg.replace('"', "'")
            subprocess.run(
                ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"'],
                check=False,
            )
        elif os_name == "Linux":
            subprocess.run(["notify-send", title, msg], check=False)
        elif os_name == "Windows":
            safe_title = title.replace("'", "''")
            safe_msg = msg.replace("'", "''")
            ps_cmd = (
                "$w = 'C:\\Windows\\Media\\Windows Notify System Generic.wav'; "
                "if (-not (Test-Path $w)) { $w = 'C:\\Windows\\Media\\tada.wav' }; "
                "if (Test-Path $w) { (New-Object Media.SoundPlayer $w).PlaySync() }; "
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, '{safe_title}', '{safe_msg}', [System.Windows.Forms.ToolTipIcon]::Info)"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=False)
    except Exception:
        pass


def audit_ad_hoc_post(
    text: str,
    platform_name: str = "Facebook/Classifieds",
    account_age_days: int | None = None,
    local_signals: int = 0,
) -> TicketListing:
    """Score any pasted Facebook Marketplace, Facebook Group, or Craigslist post/DM."""
    seller = SellerProfile(
        platform=platform_name,
        username="manual-check",
        account_age_days=account_age_days,
        local_bay_area_signals=local_signals,
    )
    listing = TicketListing(
        id="manual-audit",
        platform=platform_name,
        title=text.splitlines()[0][:80] if text else "Manual Ticket Post",
        url="N/A",
        body=text,
        posted_utc=datetime.now(timezone.utc).isoformat(),
        seller=seller,
    )
    return score_listing(listing)


def load_seen_ids() -> set[str]:
    if CACHE_FILE.exists():
        try:
            return set(json.loads(CACHE_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen_ids(seen: set[str]) -> None:
    CACHE_FILE.write_text(json.dumps(sorted(seen), indent=2))


def load_saved_listings() -> list[dict[str, Any]]:
    if RESULTS_FILE.exists():
        try:
            return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def update_dashboard(all_discovered: list[TicketListing], last_scan_str: str) -> None:
    """Save full listing history to JSON and generate an auto-refreshing HTML dashboard."""
    learned_kws = learn_keywords_from_listings(all_discovered)
    active_terms_str = ", ".join(f'"{t}"' for t in get_active_search_terms())
    learned_str = (", ".join(f'"{k}"' for k in learned_kws) if learned_kws else "None yet (scanning posts...)")
    existing = {item["id"]: item for item in load_saved_listings() if "id" in item}
    for item in all_discovered:
        existing[item.id] = asdict(item)

    sorted_items = sorted(existing.values(), key=lambda x: (x.get("scam_score", 50), x.get("posted_utc", "")))
    RESULTS_FILE.write_text(json.dumps(sorted_items, indent=2), encoding="utf-8")

    def _is_displayable(item: dict[str, Any]) -> bool:
        """Hide irrelevant filtered items (wrong weekend, costumes/items, buyer ISOs, already SOLD).
        Only show actual Saturday Oct 24 ticket seller posts AND posts filtered out as Likely Scams."""
        r_level = str(item.get("risk_level", ""))
        if not r_level.startswith("FILTERED OUT"):
            return True
        low_r = r_level.lower()
        if "likely scam" in low_r:
            return True
        # Hide non-scam irrelevant items
        if any(irrel in low_r for irrel in (
            "wrong faire date", "archived post", "past faire weekend", "wrong renaissance faire",
            "physical costume", "armor", "buyer", "iso ", "already marked", "general faire",
            "search index snippet", "does not offer", "rule notice"
        )):
            return False
        return "scam" in low_r or "bot" in low_r

    visible_items = [x for x in sorted_items if _is_displayable(x)]

    low_count = sum(1 for x in visible_items if x.get("scam_score", 0) < 35)
    med_count = sum(1 for x in visible_items if 35 <= x.get("scam_score", 0) < 60)
    high_count = sum(1 for x in visible_items if x.get("scam_score", 0) >= 60)

    rows_html = []
    for item in visible_items:
        score = int(item.get("scam_score", 0))
        r_level = str(item.get("risk_level", ""))
        if r_level.startswith("FILTERED OUT"):
            badge_cls = "badge-high"
            verdict_short = r_level
        elif score < 35:
            badge_cls = "badge-low"
            verdict_short = "LOW RISK (Promising)"
        elif score < 60:
            badge_cls = "badge-med"
            verdict_short = "MEDIUM RISK (Verify First)"
        else:
            badge_cls = "badge-high"
            verdict_short = "HIGH RISK / FILTERED SCAM"

        price_val = item.get("price_usd")
        price_str = f"${price_val:.2f}" if price_val is not None else "Not listed"
        seller = item.get("seller") or {}
        seller_str = html.escape(str(seller.get("username") or "Unknown"))
        if seller.get("joined_year"):
            seller_str += f" <span class='sub'>(Joined {seller['joined_year']})</span>"
        elif seller.get("account_age_days") is not None:
            seller_str += f" <span class='sub'>({seller['account_age_days']}d old)</span>"
        if seller.get("local_bay_area_signals"):
            seller_str += f" <span class='tag-local'>📍 {seller['local_bay_area_signals']} Bay Area signals</span>"

        g_flags = "".join(f"<div class='flag-green'>✅ {html.escape(g)}</div>" for g in item.get("green_flags", []))
        r_flags = "".join(f"<div class='flag-red'>🚩 {html.escape(r)}</div>" for r in item.get("red_flags", []))
        url_str = html.escape(str(item.get("url") or "#"))
        title_str = html.escape(str(item.get("title") or "Untitled"))
        body_str = html.escape(str(item.get("body") or ""))[:320]
        plat_str = html.escape(str(item.get("platform") or ""))
        item_id_js = html.escape(json.dumps(str(item.get("id", ""))))

        rows_html.append(f"""
        <tr class="row-item" data-id={item_id_js} data-risk="{badge_cls}">
            <td>
                <div class="platform-pill">{plat_str}</div>
                <div class="sub" style="margin-top:6px;">{html.escape(str(item.get("posted_utc", ""))[:19].replace("T", " "))}</div>
            </td>
            <td>
                <a href="{url_str}" target="_blank" class="post-title">{title_str} ↗</a>
                <div class="post-body">{body_str}</div>
                <div class="seller-line">👤 Seller: {seller_str}</div>
            </td>
            <td class="price-cell">{price_str}</td>
            <td>
                <div class="score-wrap">
                    <span class="badge {badge_cls}">{score}% Scam Risk</span>
                    <div class="verdict-text">{verdict_short}</div>
                    <div class="progress-bar"><div class="progress-fill {badge_cls}" style="width: {max(4, score)}%;"></div></div>
                </div>
            </td>
            <td>
                {g_flags}
                {r_flags}
                {('<div class="sub">No specific flags triggered</div>' if not g_flags and not r_flags else '')}
                <div class="user-reports-box"></div>
            </td>
            <td>
                <div class="claim-status-box"></div>
                <div class="action-btns">
                    <button class="btn-claim" onclick='claimListing({item_id_js})'>💬 I'm Messaging</button>
                    <button class="btn-report" onclick='reportListing({item_id_js})'>🚨 Report Suspicious</button>
                </div>
            </td>
        </tr>
        """)

    empty_state = """
    <tr>
        <td colspan="6" style="text-align:center; padding: 48px 20px; color: #94a3b8;">
            <div style="font-size: 20px; font-weight: 600; color: #e2e8f0; margin-bottom: 8px;">
                🔍 Actively Scanning All Platforms Every 5 Minutes...
            </div>
            <div>No Saturday, Oct 24 seller posts or ISO comments found yet.</div>
        </td>
    </tr>
    """ if not rows_html else "".join(rows_html)

    try:
        from dashboard_server import load_team_state, public_state_view
        initial_team_state_json = json.dumps(public_state_view(load_team_state()))
    except Exception:
        initial_team_state_json = '{"claims":{},"reports":{},"manual_leads":[],"subscribers":[]}'

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NorCal Ren Faire (Sat Oct 24) — Live Ticket Scout & Scam Dashboard</title>
<style>
    :root {{
        --bg: #0f172a;
        --card: #1e293b;
        --border: #334155;
        --text: #f8fafc;
        --muted: #94a3b8;
        --green: #10b981;
        --amber: #f59e0b;
        --red: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
        margin: 0; padding: 28px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--bg); color: var(--text);
    }}
    .header {{
        display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap;
        background: var(--card); border: 1px solid var(--border);
        padding: 14px 20px; border-radius: 14px; margin-bottom: 12px;
    }}
    .title-area {{ flex: 1; min-width: 300px; }}
    .title-area h1 {{ margin: 0 0 4px 0; font-size: 20px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
    .title-area p {{ margin: 0; color: var(--muted); font-size: 12.5px; }}
    .status-pill {{
        background: rgba(16, 185, 129, 0.15); border: 1px solid var(--green);
        color: #34d399; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600;
    }}
    .stats {{
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px;
    }}
    .stat-card {{
        background: var(--card); border: 1px solid var(--border);
        padding: 10px 16px; border-radius: 10px; display: flex; justify-content: space-between; align-items: center;
    }}
    .stat-label {{ color: var(--muted); font-size: 12.5px; }}
    .stat-val {{ font-size: 22px; font-weight: 700; }}
    table {{
        width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 14px; overflow: hidden;
    }}
    th {{
        text-align: left; padding: 14px 16px; background: #0f172a;
        color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
        border-bottom: 1px solid var(--border);
    }}
    td {{
        padding: 16px; border-bottom: 1px solid var(--border); vertical-align: top; font-size: 14px;
    }}
    .platform-pill {{
        display: inline-block; background: #334155; color: #e2e8f0;
        padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
    }}
    .post-title {{
        color: #60a5fa; font-weight: 600; text-decoration: none; font-size: 15px;
    }}
    .post-title:hover {{ text-decoration: underline; }}
    .post-body {{ color: #cbd5e1; font-size: 13px; margin-top: 6px; white-space: pre-wrap; }}
    .seller-line {{ margin-top: 8px; font-size: 12px; color: var(--muted); }}
    .price-cell {{ font-weight: 700; font-size: 16px; color: #f8fafc; white-space: nowrap; }}
    .badge {{
        display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 700;
    }}
    .badge-low {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
    .badge-med {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #d97706; }}
    .badge-high {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }}
    .verdict-text {{ font-size: 12px; color: var(--muted); margin-top: 6px; font-weight: 600; }}
    .progress-bar {{
        width: 140px; height: 6px; background: #334155; border-radius: 99px; margin-top: 8px; overflow: hidden;
    }}
    .progress-fill.badge-low {{ background: var(--green); border: none; }}
    .progress-fill.badge-med {{ background: var(--amber); border: none; }}
    .progress-fill.badge-high {{ background: var(--red); border: none; }}
    .flag-green {{ color: #34d399; font-size: 12.5px; margin-bottom: 4px; }}
    .flag-red {{ color: #f87171; font-size: 12.5px; margin-bottom: 4px; }}
    .sub {{ color: var(--muted); font-size: 12px; }}
    .tag-local {{
        background: rgba(59, 130, 246, 0.2); color: #93c5fd; padding: 2px 6px;
        border-radius: 4px; font-size: 11px; margin-left: 4px;
    }}
    .action-btns {{ display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }}
    .btn-claim, .btn-report {{
        cursor: pointer; border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 600;
        border: 1px solid var(--border); text-align: left; transition: 0.15s;
    }}
    .btn-claim {{ background: rgba(59, 130, 246, 0.15); color: #93c5fd; border-color: #2563eb; }}
    .btn-claim:hover {{ background: rgba(59, 130, 246, 0.3); }}
    .btn-report {{ background: rgba(239, 68, 68, 0.12); color: #fca5a5; border-color: #dc2626; }}
    .btn-report:hover {{ background: rgba(239, 68, 68, 0.28); }}
    .claim-pill {{
        display: inline-block; background: rgba(59, 130, 246, 0.25); border: 1px solid #3b82f6;
        color: #bfdbfe; padding: 5px 9px; border-radius: 6px; font-size: 12px; font-weight: 600; margin-bottom: 6px;
    }}
    .report-pill {{
        background: rgba(239, 68, 68, 0.25); border: 1px solid #ef4444;
        color: #fecaca; padding: 5px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; margin-top: 6px;
    }}
    .alert-side {{
        background: rgba(15, 23, 42, 0.75); border: 1px solid #334155;
        border-radius: 10px; padding: 10px 14px; width: 430px; max-width: 100%;
        display: flex; flex-direction: column; gap: 6px;
    }}
    .alert-top {{
        display: flex; justify-content: space-between; align-items: center; gap: 8px;
    }}
    .alert-form {{
        display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
    }}
    .alert-input {{
        background: #0f172a; border: 1px solid var(--border); color: var(--text);
        padding: 5px 8px; border-radius: 6px; font-size: 12px;
    }}
    .alert-input:focus {{ outline: none; border-color: #60a5fa; }}
    .btn-sub {{
        cursor: pointer; background: #2563eb; color: #ffffff; border: 1px solid #3b82f6;
        padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; transition: 0.15s; white-space: nowrap;
    }}
    .btn-sub:hover {{ background: #1d4ed8; }}
    .btn-push {{
        cursor: pointer; background: rgba(16, 185, 129, 0.14); color: #34d399; border: 1px solid #059669;
        padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-decoration: none;
        display: inline-block; transition: 0.15s; white-space: nowrap;
    }}
    .btn-push:hover {{ background: rgba(16, 185, 129, 0.28); }}
    .sub-pill {{
        display: inline-flex; align-items: center; gap: 4px;
        background: rgba(59, 130, 246, 0.14); border: 1px solid #334155;
        color: #cbd5e1; padding: 2px 7px; border-radius: 999px; font-size: 11px; margin-right: 4px; margin-top: 2px;
    }}
    .sub-del {{
        cursor: pointer; color: #f87171; font-weight: 700; border: none; background: none; padding: 0 2px; font-size: 11px;
    }}
</style>
</head>
<body>
    <div class="header">
        <div class="title-area">
            <h1>
                <span>🏰 NorCal Ren Faire (Sat, Oct 24, 2026) — Ticket Scout</span>
                <span class="status-pill">● Live | Last Sweep: {last_scan_str}</span>
            </h1>
            <p>Monitoring Pretix, Etix, VouchFirst, 9 Craigslists, Reddit, Nextdoor, Brokers, FB Marketplace & 5 FB Groups</p>
            <p style="margin-top:4px; font-size:11.5px; color:#93c5fd;">🔎 <b>Search Terms:</b> {html.escape(active_terms_str)} &nbsp;|&nbsp; 🧠 <b>Auto-Learned:</b> {html.escape(learned_str)}</p>
        </div>

        <div class="alert-side">
            <div class="alert-top">
                <span style="font-size:12.5px; font-weight:700; color:#f8fafc;">🔔 Instant New-Listing Alerts</span>
                <div style="display:flex; gap:5px;">
                    <a href="https://ntfy.sh/norcal_renfaire_oct24_tickets" target="_blank" class="btn-push" title="Open mobile push feed">📱 Push Feed</a>
                    <button type="button" class="btn-push" id="btnBrowserPush" onclick="enableBrowserNotifications()">🔊 Sound Alert</button>
                </div>
            </div>
            <form class="alert-form" onsubmit="subscribeAlerts(event)">
                <input type="text" id="subName" class="alert-input" placeholder="Name" style="width:78px;" required>
                <input type="tel" id="subPhone" class="alert-input" placeholder="Phone #" style="width:105px;">
                <input type="email" id="subEmail" class="alert-input" placeholder="or Email" style="width:125px;">
                <button type="submit" class="btn-sub">📲 Sign Up</button>
            </form>
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                <div id="subscribersListBox" class="sub" style="font-size:11px;"></div>
                <span id="subMsg" class="sub" style="font-size:11px;"></span>
            </div>
        </div>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-label">Sat Oct 24 Leads (excl. {len(sorted_items) - len(visible_items)} irrelevant)</div>
            <div class="stat-val">{len(visible_items)}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label" style="color:#34d399;">Low Risk (&lt;35%)</div>
            <div class="stat-val" style="color:#34d399;">{low_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label" style="color:#fbbf24;">Medium Risk (35–59%)</div>
            <div class="stat-val" style="color:#fbbf24;">{med_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label" style="color:#f87171;">Filtered Likely Scams (60%+)</div>
            <div class="stat-val" style="color:#f87171;">{high_count}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 140px;">Platform & Time</th>
                <th>Identified Post / Comment & Seller</th>
                <th style="width: 90px;">Price</th>
                <th style="width: 170px;">Scam % & Verdict</th>
                <th style="width: 300px;">Green & Red Flags + Reports</th>
                <th style="width: 175px;">Group Coordination</th>
            </tr>
        </thead>
        <tbody>
            {empty_state}
        </tbody>
    </table>

<script>
let isDialogOpen = false;
let API_BASE = '';
const INITIAL_TEAM_STATE = {initial_team_state_json};

function esc(s) {{
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

function renderTeamState(state) {{
    if (!state) return;
    const subs = state.subscribers || [];
    const subBox = document.getElementById('subscribersListBox');
    if (subBox) {{
        if (subs.length === 0) {{
            subBox.innerHTML = '👥 0 signed up for alerts';
        }} else {{
            subBox.innerHTML = '👥 <b>' + subs.length + ' signed up:</b> ' + subs.map(s => {{
                const contact = [s.masked_phone || '', s.masked_email || ''].filter(Boolean).join(' / ');
                return `<span class="sub-pill"><b>${{esc(s.name)}}</b> (${{esc(contact)}}) <button class="sub-del" title="Unsubscribe" onclick="unsubscribeAlert('${{esc(s.id)}}')">✕</button></span>`;
            }}).join('');
        }}
    }}
    document.querySelectorAll('tr.row-item').forEach(row => {{
        const id = row.getAttribute('data-id');
        const claimBox = row.querySelector('.claim-status-box');
        const reportBox = row.querySelector('.user-reports-box');
        const claim = (state.claims || {{}})[id];
        if (claim && claim.name) {{
            claimBox.innerHTML = `<div class="claim-pill">💬 <b>${{esc(claim.name)}}</b>: ${{esc(claim.status)}} <span class="sub">(${{esc(claim.updated_at)}})</span></div>`;
        }} else {{
            claimBox.innerHTML = `<div class="sub" style="margin-bottom:4px;">Nobody messaging yet</div>`;
        }}
        const reports = (state.reports || {{}})[id] || [];
        if (reports.length > 0) {{
            reportBox.innerHTML = reports.map(r => `<div class="report-pill">🚨 <b>Reported by ${{esc(r.reporter)}}:</b> ${{esc(r.reason)}} <span class="sub">(${{esc(r.time)}})</span></div>`).join('');
            row.style.background = 'rgba(239, 68, 68, 0.08)';
        }} else {{
            reportBox.innerHTML = '';
            row.style.background = '';
        }}
    }});
}}

async function checkLiveTunnelFromGitHubPages() {{
    if (!window.location.hostname.endsWith('github.io')) return;
    try {{
        const r = await fetch('https://ntfy.sh/norcal_renfaire_oct24_tunnel_url/json?poll=1&t=' + Date.now());
        const t = await r.text();
        const lines = t.trim().split('\n').filter(Boolean);
        let tunnelUrl = '';
        for (let i = lines.length - 1; i >= 0; i--) {{
            try {{
                const obj = JSON.parse(lines[i]);
                if (obj && obj.message && obj.message.startsWith('https://')) {{
                    tunnelUrl = obj.message.replace(/\\/+$/, '');
                    break;
                }}
            }} catch (e) {{}}
        }}
        if (!tunnelUrl) return;
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 2500);
        const ping = await fetch(tunnelUrl + '/api/state?t=' + Date.now(), {{ signal: ctrl.signal }});
        clearTimeout(timer);
        if (ping.ok) {{
            API_BASE = tunnelUrl;
            const state = await ping.json();
            renderTeamState(state);
            // Also hot-sync latest table & stats from live server without leaving github.io
            const htmlRes = await fetch(tunnelUrl + '/dashboard.html?t=' + Date.now());
            if (htmlRes.ok) {{
                const htmlText = await htmlRes.text();
                const doc = new DOMParser().parseFromString(htmlText, 'text/html');
                const newStats = doc.querySelector('.stats');
                const newTbody = doc.querySelector('table tbody');
                const newPill = doc.querySelector('.status-pill');
                if (newStats && document.querySelector('.stats')) {{
                    document.querySelector('.stats').innerHTML = newStats.innerHTML;
                }}
                if (newTbody && document.querySelector('table tbody')) {{
                    document.querySelector('table tbody').innerHTML = newTbody.innerHTML;
                }}
                if (newPill && document.querySelector('.status-pill')) {{
                    document.querySelector('.status-pill').textContent = newPill.textContent;
                }}
                renderTeamState(state);
            }}
        }}
    }} catch (e) {{
        const pill = document.querySelector('.status-pill');
        if (pill && !pill.textContent.includes('Saved Snapshot')) {{
            pill.textContent = '● Saved Snapshot (Auto-Syncs When Scanner Sweep Completes)';
        }}
    }}
}}

function playTicketChime() {{
    try {{
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [523.25, 659.25, 783.99, 1046.50].forEach((freq, idx) => {{
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.12, ctx.currentTime + idx * 0.12);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + idx * 0.12 + 0.35);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(ctx.currentTime + idx * 0.12);
            osc.stop(ctx.currentTime + idx * 0.12 + 0.35);
        }});
    }} catch (e) {{}}
}}

async function enableBrowserNotifications() {{
    const btn = document.getElementById('btnBrowserPush');
    if ('Notification' in window) {{
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {{
            localStorage.setItem('renfaire_browser_push', '1');
            btn.textContent = '✅ Browser Push & Sound Active';
            playTicketChime();
            new Notification('🏰 NorCal Ren Faire Ticket Alerts Active!', {{
                body: 'You will get an instant alert + chime when a Saturday Oct 24 ticket is found.'
            }});
            return;
        }}
    }}
    localStorage.setItem('renfaire_browser_push', '1');
    btn.textContent = '✅ Sound Chime Active';
    playTicketChime();
}}

function checkNewRowsForBrowserAlert() {{
    if (localStorage.getItem('renfaire_browser_push') === '1') {{
        const btn = document.getElementById('btnBrowserPush');
        if (btn) btn.textContent = '✅ Browser Push & Sound Active';
    }}
    const seenRaw = localStorage.getItem('renfaire_seen_alert_ids');
    const seenIds = new Set(seenRaw ? JSON.parse(seenRaw) : []);
    let foundNewPromising = null;
    document.querySelectorAll('tr.row-item').forEach(row => {{
        const id = row.getAttribute('data-id');
        const risk = row.getAttribute('data-risk');
        if (id && !seenIds.has(id)) {{
            seenIds.add(id);
            if (risk === 'badge-low' || risk === 'badge-med') {{
                const titleEl = row.querySelector('.post-title');
                foundNewPromising = titleEl ? titleEl.textContent : 'New Saturday Oct 24 Ticket Lead!';
            }}
        }}
    }});
    localStorage.setItem('renfaire_seen_alert_ids', JSON.stringify(Array.from(seenIds)));
    if (foundNewPromising && seenRaw && localStorage.getItem('renfaire_browser_push') === '1') {{
        playTicketChime();
        if ('Notification' in window && Notification.permission === 'granted') {{
            new Notification('🏰 New Sat Oct 24 Ticket Found!', {{ body: foundNewPromising }});
        }}
    }}
}}

async function subscribeAlerts(ev) {{
    ev.preventDefault();
    const name = document.getElementById('subName').value.trim();
    const phone = document.getElementById('subPhone').value.trim();
    const email = document.getElementById('subEmail').value.trim();
    const msgEl = document.getElementById('subMsg');
    if (!phone && !email) {{
        msgEl.style.color = '#f87171';
        msgEl.textContent = 'Enter a 10-digit phone number or email address.';
        return;
    }}
    if (name) localStorage.setItem('renfaire_user_name', name);
    msgEl.style.color = '#93c5fd';
    msgEl.textContent = 'Subscribing...';
    try {{
        const res = await fetch(API_BASE + '/api/subscribe', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{name, phone, email}})
        }});
        const data = await res.json();
        if (!data.ok) {{
            msgEl.style.color = '#f87171';
            msgEl.textContent = data.error || 'Could not subscribe.';
        }} else {{
            msgEl.style.color = '#34d399';
            msgEl.textContent = '✅ Subscribed to instant ticket alerts!';
            document.getElementById('subPhone').value = '';
            document.getElementById('subEmail').value = '';
            syncTeamState();
        }}
    }} catch (e) {{
        msgEl.style.color = '#f87171';
        msgEl.textContent = 'Host PC is currently asleep — try again in a few minutes.';
    }}
}}

async function unsubscribeAlert(id) {{
    if (!confirm('Remove this alert subscription?')) return;
    await fetch(API_BASE + '/api/unsubscribe', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{id}})
    }});
    syncTeamState();
}}

async function syncTeamState() {{
    try {{
        const res = await fetch(API_BASE + '/api/state?t=' + Date.now());
        if (!res.ok) return;
        const state = await res.json();
        renderTeamState(state);
    }} catch (e) {{}}
}}

async function claimListing(id) {{
    isDialogOpen = true;
    try {{
        const savedName = localStorage.getItem('renfaire_user_name') || '';
        const name = prompt("Enter your name (leave blank to clear/unclaim):", savedName);
        if (name === null) return;
        if (name.trim()) localStorage.setItem('renfaire_user_name', name.trim());
        let status = "Messaging Seller";
        if (name.trim()) {{
            status = prompt("Status (e.g., 'Messaging Seller', 'Verifying', 'Bought Tickets!'):", "Messaging Seller") || "Messaging Seller";
        }}
        await fetch(API_BASE + '/api/claim', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id, name: name.trim(), status}})
        }});
        syncTeamState();
    }} finally {{
        isDialogOpen = false;
    }}
}}

async function reportListing(id) {{
    isDialogOpen = true;
    try {{
        const savedName = localStorage.getItem('renfaire_user_name') || '';
        const name = prompt("Your name:", savedName) || "Friend";
        if (name.trim()) localStorage.setItem('renfaire_user_name', name.trim());
        const reason = prompt("Why is this seller suspicious? (e.g., 'Refused PayPal G&S', 'Sent fake screenshot', 'Asked for Zelle'):");
        if (!reason) return;
        await fetch(API_BASE + '/api/report', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id, name: name.trim(), reason: reason.trim()}})
        }});
        syncTeamState();
    }} finally {{
        isDialogOpen = false;
    }}
}}

const savedUser = localStorage.getItem('renfaire_user_name');
if (savedUser && document.getElementById('subName')) {{
    document.getElementById('subName').value = savedUser;
}}
renderTeamState(INITIAL_TEAM_STATE);
checkLiveTunnelFromGitHubPages();
checkNewRowsForBrowserAlert();
syncTeamState();
setInterval(syncTeamState, 3000);
setInterval(checkLiveTunnelFromGitHubPages, 15000);
setInterval(() => {{
    const activeTag = document.activeElement ? document.activeElement.tagName : '';
    const isTyping = ['INPUT', 'SELECT', 'TEXTAREA'].includes(activeTag);
    if (!isDialogOpen && !isTyping) window.location.reload();
}}, 45000);
</script>
</body>
</html>"""
    DASHBOARD_FILE.write_text(html_doc, encoding="utf-8")
    if DASHBOARD_FILE == Path("dashboard.html"):
        Path("index.html").write_text(html_doc, encoding="utf-8")
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "index.html").write_text(html_doc, encoding="utf-8")
        sync_github_pages_snapshot(html_doc, visible_items, initial_team_state_json)


def sync_github_pages_snapshot(html_doc: str, visible_items: list[dict[str, Any]], team_state_json: str) -> None:
    """Keep docs/index.html on GitHub Pages updated whenever visible listings or team state change."""
    try:
        import base64
        sig_payload = json.dumps([x.get("id") for x in visible_items], sort_keys=True) + "|" + team_state_json
        sig_hash = stable_id_hash(sig_payload)
        sig_file = Path(".last_gh_pages_hash")
        if sig_file.exists() and sig_file.read_text(encoding="utf-8").strip() == sig_hash:
            return
        gh_exe = Path(r"C:\Program Files\GitHub CLI\gh.exe")
        if not gh_exe.exists():
            return
        sig_file.write_text(sig_hash, encoding="utf-8")
        repo = "slizha99/renfaire-ticket-scout"
        rel = "docs/index.html"
        content_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("ascii")
        r_get = subprocess.run([str(gh_exe), "api", f"repos/{repo}/contents/{rel}", "--jq", ".sha"], capture_output=True, text=True, timeout=8)
        sha = r_get.stdout.strip() if r_get.returncode == 0 else None
        payload: dict[str, Any] = {"message": "Auto-sync static dashboard fallback snapshot to GitHub Pages", "content": content_b64}
        if sha:
            payload["sha"] = sha
        subprocess.run([str(gh_exe), "api", "--method", "PUT", f"repos/{repo}/contents/{rel}", "--input", "-"], input=json.dumps(payload), capture_output=True, text=True, timeout=12)
    except Exception:
        pass


def print_listing_report(listing: TicketListing) -> None:
    print("=" * 76)
    print(f"[{listing.platform}] {listing.title}")
    print(f"URL: {listing.url}")
    print(f"Price: {f'${listing.price_usd:.2f}' if listing.price_usd else 'Not listed (ask seller)'}")
    print(f"Scam Score: {listing.scam_score}/100 -> {listing.risk_level}")
    if listing.seller and listing.seller.username != "manual-check":
        s = listing.seller
        age_str = (
            f"joined {s.joined_year}"
            if s.joined_year
            else (f"{s.account_age_days}d old" if s.account_age_days is not None else "age unknown")
        )
        karma_str = (
            f"karma={(s.post_karma or 0) + (s.comment_karma or 0)}"
            if s.post_karma is not None
            else ""
        )
        print(f"Seller: {s.username} ({age_str} {karma_str}) {s.profile_url}")
    if listing.green_flags:
        print("Green Flags:")
        for gf in listing.green_flags:
            print(f"  [+] {gf}")
    if listing.red_flags:
        print("Red Flags:")
        for rf in listing.red_flags:
            print(f"  [!] {rf}")
    print(
        "Next Step: Ask for a continuous screen recording opening the Etix email "
        "(QR covered) and pay ONLY via PayPal Goods & Services."
    )


def sync_permanent_partiful_link() -> None:
    """Ensure dashboard_server + cloudflared tunnel are running and keep https://slizha99.github.io/renfaire-ticket-scout/ pointed to the active tunnel."""
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/api/state", timeout=3)
    except Exception:
        try:
            subprocess.Popen(
                [sys.executable, "-u", "dashboard_server.py"],
                cwd=str(Path(__file__).resolve().parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    active_tunnel_url = None
    for port in (20241, 20242, 20243):
        try:
            metrics = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2).read().decode("utf-8", errors="ignore")
            m = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", metrics)
            if m:
                candidate_url = m[0]
                # Verify the Cloudflare tunnel is actually reachable externally (not expired after PC sleep)
                urllib.request.urlopen(f"{candidate_url}/api/state", timeout=4)
                active_tunnel_url = candidate_url
                break
        except Exception:
            continue

    if not active_tunnel_url:
        try:
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True, timeout=4)
        except Exception:
            pass
        try:
            cf_exe = Path(__file__).resolve().parent / "cloudflared.exe"
            if cf_exe.exists():
                subprocess.Popen(
                    [str(cf_exe), "tunnel", "--url", "http://127.0.0.1:8765", "--metrics", "127.0.0.1:20241"],
                    cwd=str(Path(__file__).resolve().parent),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for _ in range(8):
                    time.sleep(1.5)
                    try:
                        metrics = urllib.request.urlopen("http://127.0.0.1:20241/metrics", timeout=2).read().decode("utf-8", errors="ignore")
                        m = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", metrics)
                        if m:
                            active_tunnel_url = m[0]
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    if active_tunnel_url:
        try:
            req1 = urllib.request.Request(
                "https://ntfy.sh/norcal_renfaire_oct24_tunnel_url",
                data=active_tunnel_url.encode("utf-8"),
                method="PUT",
            )
            urllib.request.urlopen(req1, timeout=6)
        except Exception:
            pass


def run_scan(
    use_browser: bool = False,
    headless: bool = False,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    output_json: bool = False,
) -> list[TicketListing]:
    sync_permanent_partiful_link()
    seen = load_seen_ids()
    all_listings: list[TicketListing] = []

    all_listings.extend(check_official_etix())
    all_listings.extend(scrape_vouchfirst())
    all_listings.extend(scrape_craigslist())
    all_listings.extend(scrape_reddit())
    all_listings.extend(scrape_resale_brokers_http())
    update_dashboard(all_listings, datetime.now().strftime("%I:%M:%S %p") + " (Fast HTTP/Reddit done; starting Playwright...)")

    if use_browser:
        all_listings.extend(scrape_with_playwright(profile_dir=profile_dir, headless=headless))

    new_listings = [item for item in all_listings if item.id not in seen]
    for item in new_listings:
        seen.add(item.id)
    save_seen_ids(seen)

    now_str = datetime.now().strftime("%I:%M:%S %p")
    update_dashboard(all_listings, now_str)

    new_listings.sort(key=lambda x: x.scam_score)

    if output_json:
        print(json.dumps([asdict(item) for item in new_listings], indent=2))
    else:
        if not new_listings:
            modes = (
                "Etix, VouchFirst, Craigslist, Reddit, Brokers + Facebook/Playwright"
                if use_browser
                else "Etix, VouchFirst, Craigslist, Reddit, Brokers (HTTP)"
            )
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No new Oct 24 listings found across {modes}.")
        for item in new_listings:
            if not item.risk_level.startswith("FILTERED OUT") or "likely scam" in item.risk_level.lower():
                print_listing_report(item)
        # Only play the magical chime ONCE per scan sweep if at least one promising new listing was found
        promising_new = [
            item for item in new_listings
            if item.scam_score < 60 and not item.risk_level.startswith("FILTERED OUT")
        ]
        if promising_new:
            send_desktop_alert(promising_new[0])
            try:
                from ticket_alerts import broadcast_new_ticket_alerts
                subs: list[dict[str, Any]] = []
                state_path = Path("team_state.json")
                if state_path.exists():
                    subs = json.loads(state_path.read_text(encoding="utf-8")).get("subscribers", [])
                broadcast_new_ticket_alerts(promising_new, subs)
            except Exception:
                pass

    return new_listings


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="NorCal Ren Faire (Oct 24) Multi-Platform Ticket Scout & Scam Scorer"
    )
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Enable Playwright browser scraping for Facebook Marketplace, FB Groups, Vivid Seats, StubHub, and SeatGeek",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the Playwright browser in headless mode (after logging into Facebook once)",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Directory for persistent Chrome profile (default: .antigravity_chrome_profile)",
    )
    parser.add_argument(
        "--interval", type=int, default=300, help="Polling interval in seconds (default: 300s)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--audit-text",
        type=str,
        help="Audit a pasted Facebook/Craigslist/Reddit post or DM for scam/bot red flags",
    )
    parser.add_argument(
        "--account-age-days",
        type=int,
        default=None,
        help="Optional seller account age in days (when using --audit-text)",
    )
    parser.add_argument(
        "--local-signals",
        type=int,
        default=0,
        help="Number of local Bay Area posts/friends noticed on seller profile",
    )
    args = parser.parse_args()

    if args.audit_text:
        result = audit_ad_hoc_post(
            args.audit_text,
            account_age_days=args.account_age_days,
            local_signals=args.local_signals,
        )
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print_listing_report(result)
        return

    if args.once:
        run_scan(
            use_browser=args.browser,
            headless=args.headless,
            profile_dir=args.profile_dir,
            output_json=args.json,
        )
        return

    print(
        f"Starting NorCal Ren Faire Oct 24 Ticket Scout (polling every {args.interval}s, "
        f"browser={'ON' if args.browser else 'OFF'})..."
    )
    if platform.system() == "Windows":
        try:
            import ctypes
            # ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001): prevent idle sleep while scouting
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        except Exception:
            pass
    while True:
        run_scan(
            use_browser=args.browser,
            headless=args.headless,
            profile_dir=args.profile_dir,
            output_json=args.json,
        )
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
