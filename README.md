# 🏰 NorCal Ren Faire (Sat, Oct 24, 2026) — Ticket Scout & Scam Auditor

### 👉 **[Click Here to Open the Live Interactive Ticket Dashboard (`slizha99.github.io/renfaire-ticket-scout`)](https://slizha99.github.io/renfaire-ticket-scout/)**

Live multi-platform ticket scout, holistic post & comment evaluator, scam/bot risk scorer, and real-time collaborative web dashboard for finding **Saturday, October 24, 2026** admission tickets to the **Northern California Renaissance Faire** (Casa de Fruta / Hollister, CA).

## ✨ Features

* **Multi-Platform Discovery (Every 5 Minutes):**
  * **Official Ticketing Portals:** Pretix (`tickets.norcalrenfaire.com/PFP/NCRF2026/`) and Etix (`etix.com/ticket/v/13123/...`).
  * **VouchFirst Fan-to-Fan Exchange:** Tracks `[SELLING]` listings for Saturday, Oct 24, seller vouch status, and multi-date duplicate posts.
  * **Craigslist (9 Northern & Central CA Regions):** `sfbay`, `monterey`, `sacramento`, `stockton`, `modesto`, `fresno`, `merced`, `slo`, and `chico`.
  * **Reddit (Submissions + ISO Thread Comments):** Scans `r/Tickets`, `r/TicketResale`, `r/renfaire`, `r/bayarea`, `r/SanJose`, `r/norcal`, `r/Sacramento`, `r/santacruz`, `r/MontereyBay`, and more via PullPush API, including full comment-thread auditing under every ISO post.
  * **Facebook Marketplace & 5 Vetted Community Groups:** Scans SF, San Jose/Hollister, and Sacramento Marketplace plus *Greater Bay Area Costumers Guild (GBACG)*, *Northern California Renaissance Faire Friends*, *Bay Area Cosplay Community*, *SF Bay Area Buy Sell Swap*, and *California Ren Faire Friends* (including nested comments on ISO posts).
  * **Nextdoor, Resale Brokers & Live Web Discovery:** Checks Nextdoor, Vivid Seats, StubHub, SeatGeek, CashorTrade, Tixel, and Google 24h index.
* **Holistic Post & Comment Evaluation:**
  * Evaluates the full text and metadata (`platform`, `posted_utc`, `title`, `body`, `status_tag`, and `[Comments Audit: ...]`) holistically via LLM + cached reviews (`holistic_reviews.json`).
  * Automatically hides irrelevant posts (costumes/armor/merchandise, wrong Faire weekend, wrong city, buyer ISO posts with no sellers, already-sold listings) while surfacing **Low/Medium Risk Saturday Oct 24 leads** and **Filtered Out Likely Scams** (such as fake `"Tickets Buy, Sell & Trade"` admin groups and known scammer callouts).
* **2026 Authentic Ticket Ground-Truth Checks:**
  * Verifies official 2026 **Pretix** order links (`tickets.norcalrenfaire.com/PFP/NCRF2026/order/<5-CHAR-CODE>/`), `$42.00` all-inclusive face value (CA SB-478), PayPal Goods & Services acceptance, and local Bay Area profile signals.
* **Real-Time Group Coordination (`dashboard_server.py`):**
  * Friends can claim a lead (**`💬 I'm Messaging`** -> `'Messaging Seller'`, `'Verifying'`, `'Bought Tickets!'`) or flag a scammer (**`🚨 Report Suspicious`**), synced live across everyone's browser every 3 seconds.

## 🚀 Quick Start

```powershell
# 1. Start the interactive collaboration server (port 8765)
.\.venv\Scripts\python.exe dashboard_server.py

# 2. Start the continuous multi-platform scanner (every 300s)
.\.venv\Scripts\python.exe renfaire_ticket_scout.py --browser --headless --interval 300

# 3. Run the unit test suite
.\.venv\Scripts\python.exe -m unittest -v test_renfaire_ticket_scout.py
```
