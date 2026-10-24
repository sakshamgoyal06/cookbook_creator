# Build Plan and Checklist

> The working checklist for building what [`PRD.md`](PRD.md) describes. The PRD says **what** and **why**; this file says **in what order** and tracks **what's done**.
>
> **How to use it**
> - Work milestones top to bottom. A milestone is done when every box is ticked **and** its acceptance check passes.
> - Tick boxes (`[x]`) in the same commit as the work. Requirement IDs (e.g. `QR-3`) point to the PRD.
> - If scope changes, update the PRD first, then this plan.
> - Every code change: `flake8` clean, tests passing, run the app once locally.

**Status:** M0 in progress (tests and CI, security fixes, AI pipeline, database layer done; storage, worker and hosting next) · Last updated 2026-10-24

| Milestone | Theme | PRD refs | Target |
|---|---|---|---|
| [Phase 0](#phase-0-concierge-pilot-runs-in-parallel) | Concierge pilot (manual, in parallel) | §16 | Nov–Dec 2026 |
| [M0](#m0-foundations) | Foundations: tests, security, hosting, storage, worker, structured AI output | AI-3, AI-4, §13, §17 | Nov 2026 |
| [M1](#m1-qr-voice-playback-) | **QR voice playback** ⭐ | QR-1…QR-8 | Nov 2026 |
| [M2](#m2-whatsapp-capture) | WhatsApp capture | WA-1, WA-2, WA-5, WA-6, BUY-5 | Dec 2026 |
| [M3](#m3-follow-up-questions-and-page-back-to-mom) | Follow-up questions + page back to Mom | WA-3, WA-4, AI-5, AI-6, ENG-5 | Dec 2026 |
| [M4](#m4-reminders-that-escalate) | Reminders that escalate | ENG-1, ENG-2, ENG-3 | Jan 2027 |
| [M5](#m5-payments-and-gift-setup) | Payments + gift setup | BUY-1…BUY-5 | Jan 2027 |
| [M6](#m6-digital-cookbook-and-reveal-day) | Digital cookbook + reveal day | BOOK-1…BOOK-5, DASH-1…DASH-3 | Feb 2027 |
| [M7](#m7-upsell-admin-analytics) | Volume 2 upsell, admin, analytics | UP-1, OPS-1, OPS-3 | Feb 2027 |
| [M8](#m8-launch-readiness) | Launch readiness | §13 | Mar 2027 |

---

## Phase 0: Concierge pilot (runs in parallel)

Goal: prove families pay and Moms finish **before** automating. The founder does by hand what M2–M6 will automate.

- [ ] Landing page (one page: promise, ₹999 / launch ₹799, sample page with QR, "Book a slot") with a Razorpay payment link
- [ ] Pilot WhatsApp Business number (Business app, manual)
- [ ] Invite message templates in Hindi, Hinglish and English (PRD §7, BUY-4 wording)
- [ ] Pilot ops sheet: family, Mom's number, language, reveal date, recipes received, last activity, follow-ups sent
- [ ] Forward Mom's voice notes into the existing upload flow; send follow-up questions and page images by hand
- [ ] Add QR to pilot pages as soon as M1 lands (by hand before that, using unlisted audio links)
- [ ] Manual reminders on day 4 (Mom) and day 8 (buyer)
- [ ] Collect consent from Mom on her first message (PRIV, §13)
- [ ] **Recruit 20–50 paying families**
- [ ] Record per family: first recipe within 72 h? recipes at day 14 / 30? reached 10? asked about print / Volume 2?
- [ ] Build the AI-8 eval set as you go: 30 consented voice notes with corrected outputs
- [ ] **Pilot review:** activation ≥ 70%, completion ≥ 70%, ≥ 5 "she cried" stories → go/no-go for M2+ automation

---

## M0: Foundations

Goal: a hosted, safe, testable base that every later milestone builds on.

### Tests and CI
- [x] Add `pytest` + `tests/` with a temp-SQLite fixture and a logged-in test client (`requirements-dev.txt`)
- [x] Route tests: register/login, project CRUD, ownership checks (other user's project → redirect), recipe approve/edit, upload (mocked AI), PDF generation
- [x] Service tests: `audio_utils` (extensions, MIME fallback), `recipe_service` round-trip, `ai_service` with mocked clients
- [x] GitHub Actions: flake8 + pytest on every push to main and every PR (`.github/workflows/ci.yml`)

### Security fixes (PRD §17)
- [x] `/outputs/<filename>` replaced by `/projects/<id>/recipes/<id>/pdf`, which checks that the user owns the project and recipe
- [x] Refuse to start with a placeholder `FLASK_SECRET_KEY` when `FLASK_DEBUG` is off
- [x] CSRF protection on all POST forms (Flask-WTF `CSRFProtect`, token in every form)
- [x] Debug mode is off unless `FLASK_DEBUG` is set (`.env.example` turns it on for local development)

### AI pipeline (AI-3)
- [x] Transcription stays on `gpt-4o-transcribe`; structuring moved to Claude Sonnet 5.5 (`claude-sonnet-5-5`, effort `medium`)
- [x] Models, API keys, base URLs, max tokens, effort and temperature configurable from `.env` (`config.py`, `.env.example`)
- [x] Use structured outputs (`output_config.format` with the recipe JSON schema) instead of hand-stripping code fences
- [x] Read the text block by type, not `response.content[0]`; `temperature` is no longer sent by default (Sonnet 5.5 rejects non-default values)
- [x] Handle `stop_reason == "refusal"` and `max_tokens` with clear errors

### Infrastructure (§15)
- [x] Postgres via SQLAlchemy (or keep raw SQL with a thin adapter); migration script from SQLite schema (SQLAlchemy Core + Alembic, `scripts/migrate_sqlite_to_postgres.py`, `docs/DATABASE.md`)
- [ ] Object storage (Cloudflare R2 or S3) for audio and generated files; `storage_service` with put/get/signed-url
  - [x] `services/storage_service.py`: local backend (today's folders) and S3/R2 backend with signed URLs, set by `STORAGE_BACKEND`
  - [ ] Wire upload, transcription and PDF routes through it (after the Postgres PR, which adds `recipe_audio` and `generated_files`)
- [ ] Background worker (RQ + Redis): move transcribe → structure out of the upload request (AI-4); upload returns immediately with status `received`
- [ ] Retries with backoff for worker jobs; failures visible to ops, never shown raw to users
- [ ] Deploy to Render/Railway/Fly: web + worker + Postgres + Redis; HTTPS; env-based config
- [ ] Daily database backups enabled
- [ ] Error monitoring (Sentry free tier)

**Acceptance:** a hosted URL where a user uploads a voice note, the page returns instantly, and the recipe appears when the worker finishes; CI is green; another user can't open someone else's PDF.

---

## M1: QR voice playback ⭐

Goal: every recipe page plays Mom's real voice. This is the signature feature (PRD §8.5).

### Data
- [x] `recipes.listen_token` (≥ 128-bit, `secrets.token_urlsafe(16)`), `recipes.listen_revoked_at` (QR-3)
- [x] `recipe_audio` table: `recipe_id, storage_key, duration_s, kind (original|followup|story), play_order` (§14)
- [x] Backfill: existing recipes get a token and their `audio_filename` becomes a `recipe_audio` row

### Listen page
- [ ] Public route `/l/<token>` (no login) (QR-2): recipe title, Mom's name, recording date, one large play button, plays clips in order
- [ ] Audio served via short-lived signed URLs, never by filename (QR-5)
- [ ] Revoked token → friendly "This recording is private" page (QR-7)
- [ ] Mobile-first, big type, high contrast; < 1.5 s first paint on 4G (§13)

### QR on pages
- [ ] Add `segno` to requirements; `qr_service.make_qr(url)` → SVG/PNG, error correction ≥ M, 4-module quiet zone (QR-6)
- [ ] QR + tappable "▶ Listen to Mom" link on `recipe_detail.html` and in `cookbook_recipe_template.html` / PDF, ≥ 2 cm printed (QR-1)
- [ ] Revoke / regenerate button on the recipe page (QR-7)
- [ ] Book QR: `projects.book_token` + `/b/<token>` placeholder page listing recipes with players (QR-8; full book in M6)
- [ ] Commit to the URL format: base URL from config (`PUBLIC_BASE_URL`), path `/l/<token>` never changes without redirects (QR-4)

### Tests
- [ ] Unit: token uniqueness/length; revoked token returns the private page; no DB ids in URLs
- [ ] Route: listen page works logged out; signed URL expires

**Acceptance (PRD QR test):** print a generated page at 100% on a home inkjet; scan with iPhone Camera and Android Google Lens; Mom's voice plays within 3 s of tapping play on 4G. Revoking makes the old QR show "private".

---

## M2: WhatsApp capture

Goal: Mom sends a voice note on WhatsApp and it lands in her project with no app, login or typing.

- [ ] Meta WhatsApp Cloud API app, business number, webhook verification endpoint (`GET /webhooks/whatsapp`)
- [ ] Webhook receiver (`POST`): verify signature, store raw event, enqueue job, return 200 fast (WA-1)
- [ ] `projects.storyteller_phone` (E.164), `storyteller_name`, `storyteller_language`; route incoming numbers to their project
- [ ] Unknown numbers get a polite "this number is for family cookbooks" reply; nothing stored beyond the log
- [ ] Download media from Meta → object storage → `recipe_audio` → existing pipeline (WA-2)
- [ ] Acknowledgement within 30 s: "Got it! Writing it down… 📝" (WA-2)
- [ ] Merge notes within 10 minutes (or clear continuations) into the same recipe (WA-5)
- [ ] `wa_messages` table logging every inbound/outbound message and delivery status
- [ ] Message templates (Hindi, Hinglish, English) submitted to Meta and approved; bot language from `storyteller_language` (WA-6)
- [ ] **Consent on first contact** in Mom's language, recorded as `projects.consent_at`; no processing before consent (BUY-5, §13)
- [ ] Web upload stays as a fallback channel (DASH-5)

**Acceptance:** from a real phone, Mom gives consent, sends a 3-minute Hinglish voice note, gets an acknowledgement in < 30 s, and the structured recipe appears on the buyer's dashboard.

---

## M3: Follow-up questions and page back to Mom

Goal: fix "thoda sa" at the source and give Mom an instant reward she wants to forward.

- [ ] `recipe_questions` table (§14)
- [ ] Question generator: top ≤ 3 `unclear_items_for_review` → short questions in Mom's language (AI-5)
- [ ] Send questions on WhatsApp; status `awaiting_mom` (DASH-3)
- [ ] Voice/text answers attached to the recipe; re-structure merges answers and clears resolved items (AI-6)
- [ ] Unanswered after 48 h → left for the buyer to resolve on the review page (WA-3)
- [ ] Render the recipe page to PNG (WeasyPrint → PDF → image, or HTML → image) with Mom's name and the QR
- [ ] Send the page image to Mom with progress "Page 4 of 10 done 🎉" (WA-4)
- [ ] Milestone messages: first page, halfway, done, to Mom and buyer (ENG-5)
- [ ] p90 voice note → page back ≤ 5 minutes, measured

**Acceptance:** a voice note with a vague quantity triggers one question; Mom answers by voice; the updated page comes back to her as an image with a working QR within 5 minutes.

---

## M4: Reminders that escalate

Goal: the main defence against Mom stopping.

- [ ] Suggested dish list (10–15) entered by the buyer during setup; stored per project (ENG-3)
- [ ] Scheduler (RQ scheduler / cron worker) evaluating every project daily
- [ ] Day 4 without a recipe → warm nudge to Mom suggesting a specific dish from the list (ENG-1)
- [ ] Day 8 → message the **buyer**: "Mom has gone quiet. Call her, or cook together and record?" (ENG-1)
- [ ] Day 14 → offer Interview Mom for Me (copy only until UP-3 exists)
- [ ] Quiet hours 9 pm–9 am in Mom's time zone; "stop" pauses all reminders immediately (`projects.reminders_paused`) (ENG-2)
- [ ] Buyer can adjust or pause the schedule from the dashboard
- [ ] Unit tests for the schedule logic (time-zone and quiet-hours edges)

**Acceptance:** with the clock moved forward in tests, the right message goes to the right person on day 4/8/14, never in quiet hours, never after "stop".

---

## M5: Payments and gift setup

Goal: a buyer can pay ₹999 and set up the gift without help.

- [ ] `orders` table; `projects.tier`, `recipe_quota`, `payment_status` (§14)
- [ ] Razorpay Checkout (UPI, cards, netbanking) for Top 10 ₹999 / launch ₹799 and Family Edition ₹1,999 (BUY-2)
- [ ] Payment webhook (signature-verified) unlocks the project; idempotent on retries
- [ ] GST-ready invoice (PDF/email) per order
- [ ] Gift setup wizard: Mom's name and address form ("Sunita ji", "Mummy"), WhatsApp number, language, occasion, **reveal date**, title, dedication, dish list (BUY-3)
- [ ] Invite generator: pre-written message in Mom's language as a `wa.me` link from the buyer's own WhatsApp + shareable gift-card image (BUY-4)
- [ ] Refund path (manual via admin is fine for now)

**Acceptance:** a new user pays with UPI in Razorpay test mode, completes the wizard, taps "Send invite to Mom", and WhatsApp opens with the message pre-filled in Hindi.

---

## M6: Digital cookbook and reveal day

Goal: the thing people pay for: a finished, beautiful book the whole family opens together.

### Dashboard and review
- [ ] Project dashboard: x of N recipes, statuses, Mom's last activity, days to reveal (DASH-1)
- [ ] Recipe status flow `received → transcribed → structured → awaiting_mom → needs_review → approved` (DASH-3)
- [ ] Recipe edit as a **form** (ingredient and step rows), not raw JSON; audio player + transcript + open questions on the review page (DASH-2)

### Book
- [ ] Book compiler: cover (title, Mom's name, optional photo), dedication, contents, recipe pages with QR, About Mom, closing page (BOOK-1)
- [ ] Screen PDF (A5/square for phones) (BOOK-2)
- [ ] Private web cookbook `/b/<token>`: mobile-first, inline audio per recipe (BOOK-2, completes QR-8)
- [ ] Recipe-card images (one per recipe) with small QR and branding for forwarding (BOOK-4)
- [ ] Always ship: on reveal date compile whatever is approved; unused quota carries into Volume 2 (BOOK-5)

### Reveal day
- [ ] Scheduled reveal job on `reveal_date` (or "Reveal now" button) (BOOK-3)
- [ ] Pre-written family message + `wa.me` link for the buyer to post in family groups
- [ ] Reveal page shows the Volume 2 offer (hook for M7)

**Acceptance:** a 10-recipe project produces a PDF and web book in which every recipe's QR and link play the right voice; reveal on the set date sends the family link.

---

## M7: Upsell, admin, analytics

- [ ] Volume 2 (+10 recipes, ₹599) one-tap purchase from dashboard and reveal page (UP-1)
- [ ] Admin view: all projects, pipeline failures, stuck projects (> 10 days), WhatsApp delivery errors, refunds (OPS-1)
- [ ] Analytics events for the PRD §10 funnel: invite sent, consent, first recipe, recipe approved, reached 10, revealed, QR play, Volume 2 bought (OPS-3)
- [ ] Simple metrics page (activation, completion, median recipes at day 14/30, QR plays)

**Acceptance:** the founder can answer every PRD §10 pilot metric from the admin page without SQL.

---

## M8: Launch readiness

- [ ] Privacy policy and terms (DPDP Act 2023: Mom's consent, deletion on request, no training on audio) (§13)
- [ ] Data deletion flow (buyer or Mom request → audio, transcripts and pages removed)
- [ ] Listen-link permanence policy written down (PRD open question 3) and domain auto-renew on
- [ ] Load check: 50 voice notes arriving at once (Mother's Day spike) process within SLA
- [ ] Accessibility pass on listen and book pages on a budget Android phone
- [ ] Cost check: AI + messaging per 10-recipe book ≤ ₹250 on real pilot data (§11)
- [ ] Support playbook: what to do when Mom is stuck, payment failed, QR doesn't scan

---

## Later (P1 / P2, not scheduled)

Kept here so they aren't lost; pull them into a milestone only with evidence from the pilot.

- **P1:** WA-7 commands · WA-8 photos · WA-10 / UP-3 Interview Mom for Me · AI-7 book writing assist · AI-8 eval harness in CI · DASH-4 sections and reorder · QR-9 play counts to Mom · QR-10 clip editing · QR-11 "message from Mom" QR · QR-12 audio ZIP export · ENG-4 family dish requests · ENG-6 rescue queue · BOOK-6 themes · BOOK-7 print-ready PDF (₹299) · UP-2 tier upgrade · BUY-6 Stripe + USD · OPS-2 cost tracking · regional languages
- **P2:** BUY-7 gift for someone else · WA-9 chat-export import · UP-4 print-on-demand (India + Lulu/Gelato abroad)

---

## Decisions log

Record decisions that change the plan (newest first).

| Date | Decision | Why |
|---|---|---|
| 2026-10-24 | Database: Postgres via SQLAlchemy Core + Alembic; SQLite kept for local runs and tests; tables added milestone by milestone | Smallest change to the services; schema changes stay safe on live data |
| 2026-10-24 | Structuring moves to Claude Sonnet 5.5 at `medium` effort; transcription stays on `gpt-4o-transcribe` | Saksham's call; better structuring at a lower price per token than Sonnet 4.5 |
| 2026-10-24 | Keep `gpt-4o-transcribe` and Claude Sonnet 4.5; add structured outputs and make models and credentials configurable instead of upgrading | Transcription quality across languages matters most; swapping models stays a config change, decided by eval |
| 2026-10-24 | Digital-first at ₹999 for 10 recipes; print deferred to P2 | 60% margin after GST; low-risk test of demand |
| 2026-10-24 | QR voice playback is P0 and built right after foundations (M1) | Mom's voice is the product's signature and differentiator |
| 2026-10-24 | Removed unused code: global recipes page/route, `get_all_recipes`, the RTF build brief; renamed `openai_service` → `ai_service` | It also calls Anthropic; recipes are always viewed within a project |
