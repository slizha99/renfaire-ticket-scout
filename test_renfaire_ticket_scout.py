#!/usr/bin/env python3
"""
Comprehensive Unit Tests for NorCal Ren Faire (Sat Oct 24, 2026) Ticket Scout & Dashboard Server.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import renfaire_ticket_scout as r
import dashboard_server as ds


class TestRenFaireTicketScout(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate cache and disable live network LLM calls during deterministic unit tests
        self._orig_llm = r._call_llm_holistic_single
        self._orig_load_cache = r._load_holistic_cache
        self._orig_save_cache = r._save_holistic_cache
        r._call_llm_holistic_single = lambda summary: None
        self._mem_cache: dict = {}
        r._load_holistic_cache = lambda: self._mem_cache
        r._save_holistic_cache = lambda c: None

    def tearDown(self) -> None:
        r._call_llm_holistic_single = self._orig_llm
        r._load_holistic_cache = self._orig_load_cache
        r._save_holistic_cache = self._orig_save_cache

    def test_valid_oct24_sellers_pass_holistic_review(self) -> None:
        valid_cases = [
            (
                "[SELLING] Selling 1 general admission ticket to the Northern California Renaissance Faire 2026.",
                "Seller: Vini-vidi 7 d ago",
                "2026-10-21T20:00:00+00:00",
                "VouchFirst (Oct 24 - SELLING)",
                False,
            ),
            (
                "Selling 2 NorCal Ren Faire tickets for Saturday 10/24",
                "Can't make it anymore, selling 2 adult GA tickets for Saturday Oct 24 at face value ($42 each). PayPal G&S ok!",
                "2026-10-21T20:00:00+00:00",
                "Reddit (r/bayarea)",
                False,
            ),
            (
                "Comment by u/helpful_local",
                "I have 2 extra tickets for Saturday the 24th! Happy to send screen recording and use PayPal G&S.",
                "2026-10-21T20:00:00+00:00",
                "Reddit Comment (r/renfaire)",
                True,
            ),
        ]
        for title, body, posted, platform, is_cmt in valid_cases:
            ok, reason = r.analyze_post_holistically(
                title, body, is_comment=is_cmt, posted_utc=posted, platform=platform
            )
            self.assertTrue(ok, f"Expected valid seller for '{title}', got filtered with: {reason}")
            self.assertIsNone(reason)

    def test_costumes_armor_and_keyword_spam_rejected(self) -> None:
        merch_cases = [
            (
                "Steel Mastery Churburg Breastplate - 14th Century -XL - $300",
                "Up for sale is a used Steel Mastery Churburg Type 14th Century breastplate. Thick mild steel for HEMA / buhurt.",
            ),
            (
                "Age of Craft Milan Gauntlets - 15th Century - tempered spring steel - $375",
                "Up for sale is a pair of Age of Craft Milan Gauntlets, tempered spring steel.",
            ),
            (
                "REN FAIRE CLOTHS kids size top shirt and vest - $30 (sunnyvale)",
                "small shirt and an over period vest...$30\nren faire fair medieval cloth cloths clothing wear pleasure theo not ticket sca guild",
            ),
            (
                "New Princess Dress w/Wand - $120 (South Salinas)",
                "Beautiful lavender princess dress with wand! Well made dress by Holy Clothing size small.",
            ),
            (
                "BMW Trunk Lid Tray Tool Kit. Vintage. - $350",
                "Vintage BMW trunk lid tool kit. Tools and tray are in great condition.",
            ),
        ]
        for title, body in merch_cases:
            ok, reason = r.analyze_post_holistically(title, body, posted_utc="2026-10-21", platform="Craigslist (sfbay)")
            self.assertFalse(ok, f"Expected costume/item '{title}' to be rejected!")
            self.assertIn("physical costume / armor / item", (reason or "").lower())

    def test_wrong_dates_and_archived_posts_rejected(self) -> None:
        # 1. Explicit wrong date (10/17, 10/18, Sunday 10/25)
        ok1, r1 = r.analyze_post_holistically(
            "1 Norcal Renaissance Faire Ticket 10/17 - $100",
            "Got one ticket for Saturday 10/17.",
            posted_utc="2026-10-21",
        )
        self.assertFalse(ok1)
        self.assertIn("wrong faire date", (r1 or "").lower())

        # 2. Archived post from Oct 10 saying "for tomorrow (Saturday)?"
        ok2, r2 = r.analyze_post_holistically(
            "Tickets for sale to NorCal Ren Faire for tomorrow (Saturday)?",
            "[removed]\n[Comments Audit: 0 comments on this Reddit post — no sellers replied]",
            posted_utc="2026-10-10T02:55:56+00:00",
            platform="Reddit (r/norcal)",
        )
        self.assertFalse(ok2)
        self.assertIn("archived post from 2026-10-10", (r2 or "").lower())
        self.assertIn("0 comments on this reddit post", (r2 or "").lower())

        # 3. Post from Sunday Oct 25 saying "for today"
        ok3, r3 = r.analyze_post_holistically(
            "Selling 1 NorCal Ren Faire ticket for today!",
            "Have 1 extra ticket for today.",
            posted_utc="2026-10-25T15:00:00+00:00",
            platform="Reddit (r/renfaire)",
        )
        self.assertFalse(ok3)
        self.assertIn("sunday, oct 25", (r3 or "").lower())

    def test_other_cities_and_buyer_iso_posts_rejected(self) -> None:
        ok_vegas, r_vegas = r.analyze_post_holistically(
            "***Renaissance fair tickets in vegas** - $45 (Sacramento)",
            "4 tickets for the Renaissance fair in vegas from 9th-11th.",
            posted_utc="2026-10-21",
        )
        self.assertFalse(ok_vegas)
        self.assertIn("wrong renaissance faire", (r_vegas or "").lower())

        ok_iso, r_iso = r.analyze_post_holistically(
            "Looking for two (2) Renaissance Faire tickets for Saturday October 24",
            "willing to purchase your extra tickets!\n[Comments Audit: 0 comments on this post so far]",
            posted_utc="2026-10-21",
        )
        self.assertFalse(ok_iso)
        self.assertIn("buyer", (r_iso or "").lower())
        self.assertIn("0 comments on this post", (r_iso or "").lower())

    def test_scam_groups_and_scammer_callouts_marked_likely_scam(self) -> None:
        scam_cases = [
            (
                "Google Live Web Search (Past 24h): Facebook · The Northern California Renaissance Faire 2026 | Tickets Buy, Sell & Trade",
                "Facebook · The Northern California Renaissance Faire 2026 | Tickets Buy, Sell & Trade",
                "Google Live Web Search (Past 24h)",
            ),
            (
                "Google Live Web Search (Past 24h): GROUP ADMIN HERE RENAISSANCE FAIRE 2026",
                "GROUP ADMIN HERE RENAISSANCE FAIRE 2026",
                "Google Live Web Search (Past 24h)",
            ),
            (
                "U/Niels_h_ scammer!",
                "Scammed me out of 17 bucks for norcal renfaire tickets sent the payment and he claimed it didn't go through",
                "Reddit (r/TicketResale)",
            ),
        ]
        for title, body, plat in scam_cases:
            ok, reason = r.analyze_post_holistically(title, body, posted_utc="2026-10-21", platform=plat)
            self.assertFalse(ok)
            self.assertIn("likely scam", (reason or "").lower())

    def test_scam_scoring_and_2026_pretix_verification(self) -> None:
        # Legitimate seller with Pretix proof + PayPal G&S + local signals
        good = r.TicketListing(
            id="test-good",
            platform="FB Group: NorCal Ren Faire Friends",
            title="Selling 2 GA tickets for Saturday Oct 24 ($84 total)",
            url="https://facebook.com",
            body="Can show Pretix order at tickets.norcalrenfaire.com/PFP/NCRF2026/order/BLEXX/ and accept PayPal G&S.",
            posted_utc="2026-10-21",
            price_usd=84.0,
            seller=r.SellerProfile(platform="Facebook", username="alice", joined_year=2016, local_bay_area_signals=3),
        )
        scored_good = r.score_listing(good)
        self.assertLess(scored_good.scam_score, 15)
        self.assertTrue(any("Pretix" in g for g in scored_good.green_flags))

        # Scammer demanding Zelle/F&F with new account
        bad = r.TicketListing(
            id="test-bad",
            platform="Reddit (r/TicketResale)",
            title="Selling Oct 24 tickets kindly DM",
            url="https://reddit.com",
            body="Kindly DM me if interested. Accepting Zelle or PayPal Friends and Family only. Selling my Fairever Pass.",
            posted_utc="2026-10-21",
            price_usd=20.0,
            seller=r.SellerProfile(platform="Reddit", username="bot99", account_age_days=10, recent_ticket_sub_count=5),
        )
        scored_bad = r.score_listing(bad)
        self.assertGreaterEqual(scored_bad.scam_score, 85)
        self.assertIn("HIGH", scored_bad.risk_level)

    def test_dashboard_hides_irrelevant_and_shows_scams_and_valid_leads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(r, "RESULTS_FILE", tmp_path / "results.json"), \
                 patch.object(r, "DASHBOARD_FILE", tmp_path / "dashboard.html"), \
                 patch.object(r, "LEARNED_KEYWORDS_FILE", tmp_path / "learned.json"):
                valid_lead = r.score_listing(r.TicketListing(
                    id="lead-1", platform="VouchFirst", title="[SELLING] Oct 24 Ticket",
                    url="https://vouchfirst.com", body="Valid lead", posted_utc="2026-10-21", price_usd=42.0
                ))
                irrelevant_costume = r.mark_filtered(r.TicketListing(
                    id="irrel-1", platform="Craigslist", title="Ren Faire Costume $50",
                    url="https://craigslist.org", body="Dress", posted_utc="2026-10-21", price_usd=50.0
                ), "Selling physical costume / armor / item (costume), not event admission")
                scam_group = r.mark_filtered(r.TicketListing(
                    id="scam-1", platform="Google Live Web Search", title="Tickets Buy, Sell & Trade",
                    url="https://facebook.com", body="Fake admin group", posted_utc="2026-10-21"
                ), "Likely Scam: Dedicated 'Tickets Buy, Sell & Trade' Facebook group")

                r.update_dashboard([valid_lead, irrelevant_costume, scam_group], "Test Sweep")
                html_out = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
                self.assertIn("lead-1", html_out)
                self.assertIn("scam-1", html_out)
                self.assertNotIn("irrel-1", html_out)

    def test_stable_id_hash_and_price_extraction(self) -> None:
        self.assertEqual(r.stable_id_hash("https://example.com/1"), r.stable_id_hash("https://example.com/1"))
        self.assertEqual(r.extract_price("Tickets $42.00 each"), 42.0)
        self.assertEqual(r.extract_price("Selling for 45 bucks each"), 45.0)
        self.assertIsNone(r.extract_price("Only $3 water"))


if __name__ == "__main__":
    unittest.main()
