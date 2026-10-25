# Build Plan and Checklist

> The working checklist for building what [`PRD.md`](PRD.md) describes. The PRD says **what** and **why**. The mobile UX spec (`MOBILE_UX_SPEC.md` in project files, mockups: https://claude.ai/artifact/VM8esYT2UUWmW6Q1BKXzPa) says **how it looks**. This file says **in what order** and tracks **what's done**.
>
> **How to use it**
> - The plan is split into **modules**. Each module lists its screens (IDs from the UX spec: R = requester, C = chef/Mom, S = same person, F = family/QR), data changes, backend work, analytics events, edge cases, tests and an acceptance check.
> - The **build order** table below says which module comes next. A module is done when every box is ticked **and** its acceptance check passes.
> - Tick boxes (`[x]`) in the same commit as the work. Requirement IDs (e.g. `QR-3`) point to the PRD.
> - If scope changes, update the PRD first, then this plan.
> - Every code change: `flake8` clean, tests passing, run the app once locally. Every new table or column is an Alembic migration plus a matching `models/schema.py` change.
> - Every module emits the analytics events listed in it through `events_service.track()` (module 3). A module isn't done until its events show up on the metrics page.

**Status:** Foundations and QR voice playback built; mobile UX v1 approved as the starting point (2026-10-25); WhatsApp (module 9) on hold until Saksham says go · Last updated 2026-10-25

---

## Build order

| # | Module | Screens | PRD refs | Depends on | Status |
|---|---|---|---|---|---|
| 1 | [Foundations](#1-foundations) | | AI-3, AI-4, §13, §15, §17 | | Mostly done; deploy, backups, Sentry left |
| 2 | [Design system and app shell](#2-design-system-and-app-shell) | all | §12 | 1 | Next |
| 3 | [Analytics events](#3-analytics-events) | | OPS-3, §10 | 1 | Next (with 2) |
| 4 | [Data model v2](#4-data-model-v2) | | §14 | 1 | Next (with 2) |
| 5 | [Onboarding and gift setup](#5-onboarding-and-gift-setup) | R1–R8 | BUY-1…BUY-5, ENG-3 | 2, 3, 4 | |
| 6 | [Requester home and recipe review](#6-requester-home-and-recipe-review) | R9, R10, R13 | DASH-1…DASH-3 | 5 | |
| 7 | [Recording in the app (self and assisted)](#7-recording-in-the-app-self-and-assisted) | S1–S5 | DASH-5, QR-10 | 2, 4 | |
| 8 | [Listen pages and QR](#8-listen-pages-and-qr) | F1, F3, F5, R13 | QR-1…QR-9 | 2 | Backend done (M1), restyle left |
| 9 | [WhatsApp capture](#9-whatsapp-capture) | C1, C2 | WA-1, WA-2, WA-5, WA-6, BUY-5 | 4, 5 | **On hold** |
| 10 | [Follow-up questions and page back](#10-follow-up-questions-and-page-back) | C3, C4, S4 | WA-3, WA-4, AI-5, AI-6, ENG-5 | 7 or 9 | |
| 11 | [Reminders and escalation](#11-reminders-and-escalation) | C5, R9 card | ENG-1, ENG-2, ENG-3 | 9 | |
| 12 | [Family and dish requests](#12-family-and-dish-requests) | R11, F4 | ENG-4 | 5, 8 | |
| 13 | [Payments](#13-payments) | R3, R7 | BUY-2 | 5 | |
| 14 | [Book and reveal day](#14-book-and-reveal-day) | F2, R12 | BOOK-1…BOOK-5 | 6, 8 | |
| 15 | [Mom's page](#15-moms-page-optional-p1) | C6–C8 | | 7, 9 | P1 unless Saksham decides otherwise |
| 16 | [Upsell, admin and metrics](#16-upsell-admin-and-metrics) | | UP-1, OPS-1, OPS-3 | 3, 13 | |
| 17 | [Launch readiness](#17-launch-readiness) | | §13 | all | |

Why this order: modules 2–4 unblock every screen. Module 7 (recording in the app) needs no WhatsApp approval, so self mode and assisted mode can be tested end to end while module 9 is on hold. The Phase 0 pilot runs by hand alongside all of this.

Old milestone names, for reference: M0 = 1, M1 = 8 (backend), M2 = 9, M3 = 10, M4 = 11, M5 = 5 + 13, M6 = 6 + 14, M7 = 16, M8 = 17.

---

## Phase 0: Concierge pilot (runs in parallel)

Goal: prove families pay and cooks finish **before** automating. The founder does by hand what modules 9–14 will automate.

- [ ] Landing page (one page: promise, ₹1,200, sample page with QR, "Book a slot") with a Razorpay payment link
- [ ] Pilot WhatsApp Business number (Business app, manual)
- [ ] Invite message templates in Hindi, Hinglish and English, in the consultant voice (UX spec §1.1)
- [ ] Pilot ops sheet: family, cook's number, language, reveal date, recipes received, last activity, follow-ups sent
- [ ] Forward voice notes into the web upload; send follow-up questions and page images by hand
- [ ] Add QR to pilot pages (module 8 backend is live)
- [ ] Manual reminders on day 4 (cook) and day 8 (buyer)
- [ ] Collect consent from the cook on her first message (PRIV, §13)
- [ ] **Recruit 20–50 paying families**
- [ ] Record per family: first recipe within 72 h? recipes at day 14 / 30? reached 10? asked about print / Volume 2?
- [ ] Build the AI-8 eval set as you go: 30 consented voice notes with corrected outputs
- [ ] **Pilot review:** activation ≥ 70%, completion ≥ 70%, ≥ 5 "she cried" stories → go/no-go for full automation

---

## 1. Foundations

Goal: a hosted, safe, testable base that every later module builds on.

### Tests and CI
- [x] `pytest` + `tests/` with a temp-SQLite fixture and a logged-in test client (`requirements-dev.txt`)
- [x] Route tests: register/login, project CRUD, ownership checks, recipe approve/edit, upload (mocked AI), PDF generation
- [x] Service tests: `audio_utils`, `recipe_service`, `ai_service` with mocked clients
- [x] GitHub Actions: flake8 + pytest (SQLite and Postgres) on every push to main and every PR

### Security (PRD §17)
- [x] PDF route checks that the user owns the project and recipe (old `/outputs/<filename>` removed)
- [x] Refuse to start with a placeholder `FLASK_SECRET_KEY` when `FLASK_DEBUG` is off
- [x] CSRF protection on all POST forms
- [x] Debug mode off unless `FLASK_DEBUG` is set

### AI pipeline (AI-3)
- [x] Transcription on `gpt-4o-transcribe`; structuring on Claude Sonnet 5.5 (`claude-sonnet-5-5`, effort `medium`) with structured outputs
- [x] Models, keys, base URLs, max tokens, effort and temperature configurable from `.env`
- [x] Refusal and `max_tokens` handled with clear errors

### Infrastructure (§15)
- [x] Postgres via SQLAlchemy Core + Alembic (`docs/DATABASE.md`, `scripts/migrate_sqlite_to_postgres.py`)
- [x] `storage_service`: local backend and S3/R2 with signed URLs; upload, transcription and PDFs go through it
- [x] Background worker (RQ + Redis): upload returns at once with status `received`; inline when `REDIS_URL` is empty
- [x] Retries with backoff (30 s / 2 min / 10 min); errors in `pipeline_runs`, never shown raw to users
- [x] Railway deploy: Dockerfile, gunicorn on `$PORT`, migrations before start, `/healthz`
- [x] Installable PWA: manifest, service worker (network-first pages, offline page), icons
- [x] Product name from `APP_NAME` (working name **Andaaz**)
- [ ] Live on Railway: web + Postgres (+ Redis and worker service, + R2) with real variables (Saksham's to-do)
- [ ] `PUBLIC_BASE_URL` set to the permanent domain before any QR is printed (QR-4)
- [ ] Daily database backups enabled and one restore rehearsed
- [ ] Error monitoring (Sentry free tier) on web and worker; pipeline failures alert ops

**Acceptance:** on the hosted URL, a voice note uploads, the page returns at once, the recipe appears when the worker finishes; CI is green; another user can't open someone else's PDF or audio.

---

## 2. Design system and app shell

Goal: every new screen is built from the same small set of parts in the "Rasoi notebook" style (UX spec §1). The current UI is replaced screen by screen, not patched.

### Build
- [ ] Design tokens as CSS variables (atta, steel, tawa, curry-leaf, haldi, kumkum, chip colours) in one `static/app.css`; old `style.css` retired as screens move over
- [ ] Fonts: Tiro Devanagari Hindi (titles), Mukta (UI), Kalam (cook's quotes); `font-display: swap`; system-font fallback; never block first paint
- [ ] Jinja macros in `templates/components/`: button (primary, secondary), **record button** (kumkum only, 100–120 px), audio player (play/pause, clip list), status chip, progress ring, "needs you" card, form rows, bottom tabs, empty state, error state
- [ ] App shell with bottom tabs: requester (Home · Recipes · Record · Family · Book) and self mode (Kitchen · Record · Family · Book), picked by `projects.cook_mode`
- [ ] Copy strings in one place per language (`hi`, `hinglish`, `en`) for cook-facing surfaces, written in the consultant voice (UX spec §1.1); requester app in English, quoting her phrases verbatim
- [ ] Status-to-chip mapping in one helper (UX spec §3): received/transcribed → "Writing it down", awaiting_mom → "Waiting on Mummy" (uses `storyteller_address_as`), needs_review → "Ready to review", approved → "Approved", failed → "We couldn't hear this one" + Try again
- [ ] Touch targets ≥ 44 px (cook screens ≥ 52 px); stroke SVG icons; no emoji in UI chrome
- [ ] PWA manifest updated with the new colours; `share_target` for `audio/*` (used by S3)

### Edge cases
- [ ] Devanagari and Latin in the same line render without tofu on budget Android (test on one real device)
- [ ] Long names and titles wrap, never overflow; very long dish names truncate with the full name on tap
- [ ] Dark-mode browsers: pages keep their light palette (explicit background colours), text stays ≥ 4.5:1
- [ ] Slow network: every button that posts shows a busy state and can't be double-submitted
- [ ] JavaScript off or failing: forms still submit; audio falls back to a plain `<audio controls>`

### Tests
- [ ] Snapshot-free template tests: each macro renders with minimal data, chips map every recipe status
- [ ] Contrast check on token pairs in a unit test (simple luminance math)

**Acceptance:** the three journeys' first screen (R9, S1, F1) are built only from shell + macros and match the mockups on a 360 px Android and an iPhone.

---

## 3. Analytics events

Goal: answer every PRD §10 metric from our own data, without personal data in events (OPS-3). Moved earlier than the old M7 so every module records events from day one.

### Data
- [ ] `events` table: `id, name, project_id (nullable), recipe_id (nullable), actor (buyer|cook|family|system|anon), channel (web|pwa|whatsapp|qr|system), props JSON, created_at`; indexes on `(name, created_at)` and `(project_id, created_at)`
- [ ] `listen_events` gains `source (qr|link|book|app)` and `is_owner bool`, so owner plays can be excluded from the "voice" metric and from counts shown to the cook

### Build
- [ ] `events_service.track(name, project_id=None, recipe_id=None, actor=..., channel=..., **props)`; never raises into the request (log and continue); written in the same transaction where the action happens when possible
- [ ] Event names in one module-level catalogue (a constant per name), so a typo fails tests
- [ ] Props allowlist per event; phone numbers, names, transcripts and audio keys are rejected
- [ ] Weekly play counts: query helpers `plays_this_week(recipe_id)` and `plays_this_week(project_id)`, excluding owner plays (used by C5, C8, R13)

### Event catalogue (each module adds its own)
| Area | Events |
|---|---|
| Onboarding | `onboarding_started`, `cook_mode_chosen` {mode}, `tier_chosen` {tier}, `cook_details_saved`, `reveal_date_set` {days_away}, `dish_list_saved` {count}, `checkout_started`, `payment_succeeded` {amount_paise}, `payment_failed` {reason}, `invite_shared` {language} |
| Capture | `consent_given` {channel}, `voice_note_received` {channel, seconds}, `recording_started`, `recording_finished` {seconds}, `recording_abandoned` {seconds}, `upload_failed` {stage}, `recipe_created`, `pipeline_failed` {stage} |
| Review | `recipe_ready_for_review`, `recipe_edited` {fields_changed}, `recipe_approved` {edits}, `recipe_retry_requested` |
| Questions | `question_sent`, `question_answered` {via}, `question_skipped`, `question_expired` |
| Engagement | `reminder_sent` {day, to}, `reminders_paused` {days}, `escalation_shown`, `escalation_action` {call|record_together}, `milestone_reached` {n} |
| Family | `family_link_shared`, `family_member_joined`, `dish_requested` |
| QR / listen | `listen_page_viewed` {source}, `qr_play` {source} (from `listen_events`), `listen_link_revoked`, `listen_link_regenerated`, `qr_downloaded` {format} |
| Book | `book_compiled` {recipes}, `book_revealed`, `book_pdf_downloaded`, `book_page_viewed` |
| Upsell | `volume2_offer_shown`, `volume2_bought` |

### Edge cases
- [ ] Bots and link-preview crawlers (WhatsApp, Telegram, Slack) opening `/l/` or `/b/` don't count as views or plays (user-agent check; plays only count from the JS `played` beacon)
- [ ] One person replaying a clip 10 times in a minute counts once per page load
- [ ] Events from deleted projects are deleted with the project (DPDP deletion)
- [ ] Clock skew: always use the server time

### Tests
- [ ] Unknown event name or a banned prop raises in tests, logs in production
- [ ] Owner plays are excluded from counts shown to the cook

**Acceptance:** the metrics page (module 16) can show activation, completion and QR plays for a seeded test project using only `events` and `listen_events`.

---

## 4. Data model v2

Goal: one reviewed set of migrations for everything the new UX needs, so screens don't each invent their own columns. PRD §14 is updated to match.

Add these tables and columns (one Alembic migration per group, in this order):

- [ ] **0004 projects: cook and gift fields:** `cook_mode` (`whatsapp|self|assisted`, default `whatsapp`), `storyteller_name`, `storyteller_address_as` (what the child calls her: Mummy, Maa, Dadi), `storyteller_phone` (E.164, unique among active projects), `storyteller_language` (`hi|hinglish|en`), `occasion`, `reveal_date`, `share_pages_as_ready` (bool, default true), `consent_at`, `reminders_paused_until`, `revealed_at`
- [ ] **0005 dishes:** `id, project_id, title, position, requested_by_member_id (nullable), requested_by_label (e.g. "Riya"), source (buyer|family|cook), status (wishlist|in_progress|done|skipped), recipe_id (nullable, unique), created_at`. This replaces the PRD's separate `dish_requests` table: a family request is a dish with `source = family`
- [ ] **0006 family_members:** `id, project_id, name, role (buyer|cook|member), join_token, joined_at, removed_at`; buyer row created with the project
- [ ] **0007 recipes: dish and cook:** `recipes.dish_id` (nullable), `recipes.cook_name` (nullable; set by the Cook switcher in assisted mode, else falls back to `storyteller_name`)
- [ ] **0008 cook page token:** `projects.cook_token`, `projects.cook_token_revoked_at` (for `/m/<token>`, module 15; added now so tokens exist for every project)
- [ ] **0009 uploads:** `upload_sessions` (`id, project_id, client_upload_id unique, dish_id, bytes_expected, bytes_received, status (open|complete|abandoned), created_at`) for chunked, resumable in-app recording
- [ ] **0010 events** (module 3) and `listen_events.source`, `listen_events.is_owner`
- [ ] Later, with their modules: `orders` (13), `wa_messages` (9), `recipe_questions` (10)
- [ ] `recipe_audio.kind = story` already exists; story clips play after the recipe clips
- [ ] Backfill: existing projects get `cook_mode = self` (they were all web uploads), a cook token, a buyer `family_members` row; existing recipes get a `dishes` row each
- [ ] `docs/DATABASE.md` and `tests/test_database.py` updated (schema matches migrations)

### Edge cases
- [ ] Changing `cook_mode` after recipes exist keeps every recipe and clip; only the shell and reminders change
- [ ] Phone number entered with spaces, `+91`, `0` prefix or as 10 digits → normalised to E.164; the same number on two active projects is allowed only for the same buyer (a cook can have Volume 1 and Volume 2); otherwise blocked with a clear message
- [ ] Deleting a dish that already has a recipe unlinks it, never deletes the recipe
- [ ] Reveal date in the past or today is rejected at setup; changing it later is allowed
- [ ] All migrations run on a copy of production data before deploy, with downgrade tested

**Acceptance:** `alembic upgrade head` and `downgrade` run on SQLite and Postgres in CI; backfill leaves every existing recipe visible and playable.

---

## 5. Onboarding and gift setup

Screens: **R1** Welcome · **R2** Whose recipes? · **R3** Pick a book · **R4** Who's the cook · **R5** Occasion and reveal · **R6** Dish wishlist · **R7** Pay · **R8** Invite the cook. Same-person short setup (name on book, language, reveal date) branches from R3 into module 7.

### Build
- [ ] R1: promise, sample page with a real working "Listen" sample (a demo recording we own), sign up / log in (email + password today; Google SSO already optional)
- [ ] R2: three-way fork sets `cook_mode`: "Mummy on WhatsApp" (`whatsapp`), "My own recipes" (`self`), "I'll record her with me" (`assisted`)
- [ ] R3: tier picker (Top 10, Family Edition); prices from config, not templates (prices still open, see to-do)
- [ ] R4–R6 as a 4-step wizard with progress, each step saved on Next so a dropped connection loses nothing; Back keeps answers
- [ ] R4: what you call her, name on the cover, WhatsApp number (hidden in self mode), language
- [ ] R5: occasion chips, reveal date with "N days away" and a warning under 21 days ("That's tight for 10 recipes. We'll suggest a shorter list."), book title, dedication
- [ ] R6: 10–15 dishes, drag to reorder (with up/down buttons as the accessible fallback), suggestions by region and occasion, dish 1 goes into the invite
- [ ] R7: summary + pay (module 13); until module 13 ships, a "pilot code" path marks the project paid by hand
- [ ] R8: invite text in her language and the consultant voice, sent from the buyer's own WhatsApp via `wa.me/?text=`; gift-card image (PNG, cover style, her name, our number as QR); "I've sent it" confirmation; resend later from Home
- [ ] Self mode skips R4's phone, R8 and the gift card; lands on S1

### Events
`onboarding_started`, `cook_mode_chosen`, `tier_chosen`, `cook_details_saved`, `reveal_date_set`, `dish_list_saved`, `checkout_started`, `payment_succeeded` / `payment_failed`, `invite_shared`

### Edge cases
- [ ] Buyer quits mid-wizard → Home shows "Finish setting up" at the step they left
- [ ] Two tabs editing the same wizard → last save wins per field, no crash
- [ ] Cook's number equals the buyer's own number → allowed only in `self` or `assisted` mode; in `whatsapp` mode warn ("This is your number. Did you mean to record your own recipes?")
- [ ] Number not on WhatsApp → can't be known before sending; R8 copy says "If she doesn't have WhatsApp, record together instead" with a switch to `assisted`
- [ ] Fewer than 10 dishes → allowed (min 3), with suggestions; more than 15 → extra dishes kept as "later"
- [ ] Duplicate dish names (case, spelling, Hindi vs English) → soft warning, not blocked
- [ ] `wa.me` link too long for some Android WhatsApp versions → keep invite ≤ 1,000 characters; test in Hindi script
- [ ] Desktop buyer → `wa.me` opens WhatsApp Web; copy-text button as fallback
- [ ] Gift-card image renders Devanagari names correctly (font embedded)

### Tests
- [ ] Wizard step validation (dates, phone normalisation, dish count) unit-tested
- [ ] Each fork lands on the right home (R9 vs S1)
- [ ] Invite text renders in all three languages with her name and dish 1

**Acceptance:** a new user goes R1 → R8 on a phone in under 4 minutes, WhatsApp opens with the invite pre-filled in Hindi, and the project shows on Home with the dish list in order.

---

## 6. Requester home and recipe review

Screens: **R9** Home · **R10** Review a page · **R13** Voice link + QR (backend from module 8).

### Build
- [ ] R9 Home: progress ring (approved / quota), last voice note (who, when, play), reveal countdown, **one** "needs you" card (priority: failed recipe > ready to review > escalation > invite not sent), recipe list with chips, "Up next" dishes
- [ ] Home refreshes status without a reload while anything is "Writing it down" (poll every 10 s for 5 minutes, then stop; no websockets)
- [ ] R10 Review: player for all clips (original, follow-up, story) in order; "Recipe / What she said" toggle (structured vs transcript); ingredients and steps as **form rows** (add, remove, reorder) replacing the raw JSON editor (DASH-2); flagged approximations highlighted with "Ask her" (module 10) or "Leave as she said it"; Approve
- [ ] Approve also generates the page PDF and card image in the background (no separate Generate PDF button)
- [ ] Failed recipe: "We couldn't hear this one" chip, Try again (re-runs the pipeline from the failed stage) and "Record again" (goes to S2 or asks the cook)
- [ ] R13 restyled on the new shell (QR, play count this week and all time, save PNG/SVG, copy link, make new link, make private)
- [ ] Edits count recorded (fields changed) for the PRD quality metric

### Events
`recipe_ready_for_review`, `recipe_edited`, `recipe_approved`, `recipe_retry_requested`, `listen_link_revoked`, `listen_link_regenerated`, `qr_downloaded`

### Edge cases
- [ ] Recipe still processing when opened → R10 shows "Writing it down" and the audio player only
- [ ] Two family editors approve at once → second approve is a no-op with "Already approved"
- [ ] Editing an approved recipe → returns to "Ready to review" only if content changed; QR and link never change on edit
- [ ] Quota reached → new notes still saved (never lose a voice note) but marked "extra"; Home offers Volume 2 (module 16)
- [ ] Recipe with no structured content (pipeline failed twice) → review page offers transcript-only page or retry
- [ ] Transcript in Devanagari and English mixed → shown exactly as transcribed, no normalisation
- [ ] Very long recording (> 15 min) → player shows duration, structuring still runs (check token limits; split if needed)

### Tests
- [ ] "Needs you" card priority order
- [ ] Form-row edit round-trips ingredients and steps without JSON errors; empty rows dropped
- [ ] Retry re-runs only the failed stage

**Acceptance:** a buyer reviews and approves a Hinglish recipe on a phone without seeing JSON, in under 2 minutes, and the page PDF with a working QR appears.

---

## 7. Recording in the app (self and assisted)

Screens: **S1** My kitchen · **S2** Recording · **S3** Add notes I already have · **S4** Quick questions (engine from module 10) · **S5** Approve my page. The requester's "Record together" (escalation, assisted mode) reuses S2.

This module needs no WhatsApp approval, so it's the first full capture path to ship.

### Build
- [ ] S1: "Next up" dish with the big record button, recipe list with chips, import, Cook switcher (assisted mode: whose name and voice the page uses; sets `recipes.cook_name`)
- [ ] S2 recorder: `MediaRecorder` (webm/opus on Android Chrome, mp4/aac on iOS Safari), timer, live level meter, rotating prompt cards (static tips first; "We've heard so far" checklist is P1), Pause/Resume, "Done", "+ Add the story behind this dish" (story clip)
- [ ] Chunked, resumable upload: chunks every 10 s to `/uploads/<client_upload_id>/chunk` (idempotent by chunk index); `complete` assembles, stores via `storage_service`, creates the recipe and enqueues the pipeline
- [ ] Local safety copy in IndexedDB until the server confirms `complete`; on next open, unfinished recordings offer "Upload now"
- [ ] S3 import: Web Share Target (`audio/*`, Android) from WhatsApp → choose dish or "new dish"; file picker for iOS and desktop; several notes grouped into one dish in the order picked
- [ ] Duration (`recipe_audio.duration_s`) and content type stored for every clip
- [ ] S5 approve: final page preview with Listen + QR, "Fix something" / "Looks right", share on WhatsApp (`wa.me` with the listen link)

### Events
`recording_started`, `recording_finished`, `recording_abandoned`, `upload_failed`, `voice_note_received` {channel: app|import}, `recipe_created`, `recipe_approved`

### Edge cases
- [ ] Microphone permission denied or blocked → plain-language help per browser, and the file-picker fallback
- [ ] iOS Safari quirks: recording stops when the screen locks or the app is backgrounded → save what was recorded, show "Recording paused" on return
- [ ] Phone call or another app takes the mic mid-recording → auto-pause, keep the audio so far
- [ ] Network drops mid-upload → chunks retry with backoff; nothing deleted locally until `complete` is confirmed
- [ ] Same chunk sent twice → stored once
- [ ] Recording under 5 s → "That was very short. Keep it, or record again?"
- [ ] Recording over 30 min → warn at 25 min, stop and save at 30 min, offer to continue as part 2 of the same dish
- [ ] Silence only (level meter flat) → warn before upload
- [ ] Storage full on the phone → IndexedDB write fails → upload directly, warn that a dropped connection can lose the clip
- [ ] Unsupported format from import (e.g. `.opus` named `.ogg`, WhatsApp `.waptt`) → accepted by sniffing content type; anything else rejected with the supported list
- [ ] Imported note is very old or from another person → no check possible; keep as is
- [ ] Cook switcher changed after recording → only future recordings change; existing pages keep their cook name unless edited

### Tests
- [ ] Chunk endpoint: idempotent chunks, out-of-order chunks, abandoned sessions cleaned after 24 h
- [ ] Assembled file equals the concatenated chunks; pipeline enqueued once
- [ ] Share-target POST with 1 and 3 files creates one dish with ordered clips
- [ ] Manual device test matrix: Android Chrome (budget phone), iPhone Safari, desktop Chrome

**Acceptance:** on a budget Android phone in airplane-mode-then-online, a 4-minute recording survives the drop, uploads, and becomes a reviewed page with a working QR.

---

## 8. Listen pages and QR

Screens: **F1** Listen page · **F3** Recipe in the book · **F5** Recording made private · **R13** (owner side, in module 6).

### Done (old M1)
- [x] `recipes.listen_token` (≥ 128-bit), `listen_revoked_at`; `recipe_audio` table; backfill
- [x] Public `/l/<token>` (no login) plays clips in order; audio at `/l/<token>/audio/<n>`, signed URLs on S3/R2, never by filename (QR-2, QR-5)
- [x] Revoked or unknown token → "This recording is private" (QR-7)
- [x] `qr_service` (segno): error correction ≥ M, 4-module quiet zone; PNG/SVG downloads; QR + "Listen" link on the recipe page and in the PDF at 2.6 cm (QR-1, QR-6)
- [x] Revoke / regenerate; book QR and `/b/<token>` placeholder (QR-8); `PUBLIC_BASE_URL` (QR-4)
- [x] Plays counted in `listen_events` with no personal data
- [x] Tests: token length and uniqueness, logged-out access, no ids in URLs, signed URL expiry

### Build
- [ ] F1 restyle: "in Sunita ji's voice" (`storyteller_name`, fallback project title), recording date, 148 px play button, clip list, story clip last, "Read the recipe" (opens F3)
- [ ] F1 performance: no blocking web fonts (system font first, swap later), inline critical CSS, total page ≤ 30 KB before audio, audio `preload="none"`; first paint < 1.5 s on throttled 4G (§13)
- [ ] F3: her quote (Kalam), Listen, ingredients with her measures as said, method, QR for print
- [ ] F5: private state in English and Hindi
- [ ] `listen_events.source` set from a `?s=qr` parameter printed into QR codes (links shared from the app use `?s=link`); owner plays flagged
- [ ] Weekly play counts on R13 (QR-9 data; sending them to the cook is module 11)

### Events
`listen_page_viewed` {source}, `qr_play` {source}

### Edge cases
- [ ] Audio blocked from autoplay → always needs a tap; never autoplay
- [ ] Signed URL expires while the page is open (15 min) → player re-requests `/l/<token>/audio/<n>` on error and resumes
- [ ] Old QR printed before a regenerate → private page, never someone else's recording
- [ ] Link previews in WhatsApp show the recipe title and app name only (Open Graph tags), no audio URL
- [ ] Page opened in WhatsApp's in-app browser and in Instagram's → plays (test both)
- [ ] Project deleted → every token for it shows the private page

### Tests
- [ ] `?s=qr` is recorded; bot user agents don't create views
- [ ] Page weight budget checked in a test (HTML + CSS bytes)

**Acceptance (PRD QR test):** print a generated page at 100% on a home inkjet; scan with iPhone Camera and Android Google Lens; her voice plays within 3 s of tapping play on 4G. Revoking makes the old QR show "private".

---

## 9. WhatsApp capture

**On hold until Saksham says go** (needs a Meta WhatsApp Business account and approved templates).

Screens: **C1** Invite arrives · **C2** Consent + first note.

### Build
- [ ] Meta WhatsApp Cloud API app, business number, webhook verification (`GET /webhooks/whatsapp`)
- [ ] Webhook receiver (`POST`): verify signature, store raw event, enqueue, return 200 fast (WA-1)
- [ ] Route incoming numbers to projects by `storyteller_phone`; unknown numbers get one polite reply, nothing stored beyond the log
- [ ] **Consent first** in her language with quick replies ("Haan, shuru karein"); `consent_at` recorded; no processing before consent (BUY-5, §13)
- [ ] Media download → object storage → `recipe_audio` → pipeline; acknowledgement in < 30 s in the consultant voice ("Shukriya, aapka voice note mil gaya. Rajma likh rahe hain.") (WA-2)
- [ ] Match a note to the next dish in the list, or to the dish she names; notes within 10 minutes merge into the same recipe (WA-5)
- [ ] `wa_messages` logs every inbound/outbound message and delivery status
- [ ] Templates (Hindi, Hinglish, English) submitted and approved; bot language from `storyteller_language` (WA-6)
- [ ] Web upload and in-app recording stay as fallbacks (DASH-5)

### Events
`consent_given` {channel: whatsapp}, `voice_note_received` {channel: whatsapp}, `recipe_created`, `pipeline_failed`

### Edge cases
- [ ] Voice note sent before consent → held, consent asked, processed only after "yes"; deleted after 7 days if no consent
- [ ] She replies "no" or "stop" to consent → nothing processed, buyer told kindly, reminders off
- [ ] Text instead of voice → kept as a text recipe source ("type instead" is allowed for her too)
- [ ] Forwarded notes, images, videos, stickers, documents → audio kept; photos stored for P1 (WA-8); others get a gentle "voice note works best"
- [ ] The same note forwarded twice (same media hash) → stored once
- [ ] Very long notes (WhatsApp allows long recordings) → accepted; split for transcription if needed
- [ ] Number changed or a second phone → buyer can add a second number to the project
- [ ] Outside the 24-hour session window → only approved templates are sent
- [ ] Meta webhook retries and out-of-order delivery → idempotent on `wa_message_id`
- [ ] Media URL expired before download → retry with a fresh URL from the API

**Acceptance:** from a real phone, she gives consent, sends a 3-minute Hinglish voice note, gets the acknowledgement in < 30 s, and the recipe appears on the buyer's Home.

---

## 10. Follow-up questions and page back

Screens: **C3** Curious question · **C4** Her page comes back · **S4** Quick questions (in-app).

### Build
- [ ] `recipe_questions` table (§14)
- [ ] Question generator: top ≤ 3 `unclear_items_for_review` → short questions in her language that explain why they're asked ("Page poora karne ke liye ek baat poochni thi") (AI-5)
- [ ] One question at a time; quick replies with Indian measures (katori, mutthi, chutki, "andaaze se"), plus "Bolkar batati hoon" (voice) and "leave it as I said it"
- [ ] Answers (voice or text) attached to the recipe; re-structure merges them and clears resolved items (AI-6); answer audio stored as `kind = followup`
- [ ] Status `awaiting_mom` while questions are open (DASH-3); unanswered after 48 h → left for the buyer on R10 (WA-3)
- [ ] S4 shows the same questions in the app for self and assisted mode (owner can type)
- [ ] Page image (PNG from the PDF) with her name and the QR (C4); "Page 1 of 10 tayaar" + next dish suggestion (WA-4); only sent when `share_pages_as_ready` allows family forwarding
- [ ] Milestone messages: first page, halfway, done, to the cook and the buyer (ENG-5)
- [ ] p90 voice note → page back ≤ 5 minutes, measured from `pipeline_runs`

### Events
`question_sent`, `question_answered` {via}, `question_skipped`, `question_expired`, `milestone_reached`

### Edge cases
- [ ] "Andaaze se" / "jitna theek lage" as an answer → recorded as her answer, shown on the page as she said it, never converted to grams
- [ ] Answer arrives for an older recipe's question → matched by quoted reply, else by the most recent open question, else asks which dish
- [ ] Answer contradicts the original note → newer answer wins, both kept in the transcript
- [ ] She asks a question back ("kaunsa?") → counted as unanswered, one rephrase, then hand to the buyer
- [ ] No unclear items → no questions; page goes straight to review
- [ ] Never more than 3 questions per recipe, never more than one message in a row without her reply

**Acceptance:** a note with a vague quantity triggers one question; she answers by voice; the updated page comes back as an image with a working QR within 5 minutes.

---

## 11. Reminders and escalation

Screens: **C5** Gentle nudge · R9 "needs you" escalation card.

### Build
- [ ] Daily scheduler (RQ scheduler) evaluates every active project
- [ ] Day 4 without a recipe → nudge to the cook that leads with a fact (plays this week, who asked for which dish), then a no-pressure ask ("Koi jaldi nahi hai"), quick replies incl. "Kuch din baad yaad dilayein" (pauses 5 days) (ENG-1)
- [ ] Day 8 → R9 card for the buyer: "Mummy's been quiet 8 days. Call her, or cook together and record?" with Call (`tel:`) and Record together (S2 in assisted mode)
- [ ] Day 14 → offer "Interview Mummy for me" (copy only until UP-3 exists)
- [ ] Quiet hours 9 pm–9 am in her time zone; "stop" pauses everything (`reminders_paused_until` far future) (ENG-2)
- [ ] Buyer can change or pause the schedule from Home
- [ ] Weekly play counts go to the cook in the nudge (QR-9)

### Events
`reminder_sent` {day, to}, `reminders_paused` {days}, `escalation_shown`, `escalation_action`

### Edge cases
- [ ] Reveal date close → reminder cadence tightens but never more than one message a day
- [ ] Festival or bereavement pause → buyer can pause with one tap; resume is manual
- [ ] Self mode → reminders go to the owner only, in English, by in-app card (no WhatsApp)
- [ ] All dishes done → no reminders; offer Volume 2 instead
- [ ] Time zone unknown (diaspora) → infer from the phone country code; buyer can change it

### Tests
- [ ] Clock moved forward: the right message to the right person on day 4/8/14, never in quiet hours, never after "stop", never twice a day

**Acceptance:** in tests with a frozen clock, every rule above holds; in the pilot, ≥ 40% of stalled projects resume after an escalation.

---

## 12. Family and dish requests

Screens: **R11** Family · **F4** Join + ask for a dish.

### Build
- [ ] R11: share family link (`wa.me`), "share pages as they're ready" toggle (`share_pages_as_ready`), members list, dish requests
- [ ] F4 (no login): name + dish chips or free text; shows exactly what the cook will hear ("Riya poochh rahi hai: aloo paratha")
- [ ] Join creates a `family_members` row; a request creates a `dishes` row with `source = family`, `requested_by_member_id`
- [ ] Buyer can approve, reorder or hide requests before they reach the cook
- [ ] Nudges (module 11) and the recorder (S2) name who asked

### Events
`family_link_shared`, `family_member_joined`, `dish_requested`

### Edge cases
- [ ] Same person joins twice (same name on the same device) → one member (device cookie), duplicates mergeable by the buyer
- [ ] Rude or joke requests → buyer approval is on by default
- [ ] Family link forwarded outside the family → buyer can regenerate it; old link stops working
- [ ] Member asks for a dish already in the list → shown as "+1 asked" on the existing dish

**Acceptance:** three family members join from a shared link, each requests a dish, and the next nudge names one of them.

---

## 13. Payments

Screens: **R3** Pick a book (prices) · **R7** Pay.

### Build
- [ ] `orders` table; `projects.tier`, `recipe_quota`, `payment_status` (§14)
- [ ] Razorpay Checkout, UPI first (cards, netbanking) for the tiers and prices set in config (BUY-2)
- [ ] Signature-verified webhook unlocks the project; idempotent on retries
- [ ] GST-ready invoice per order
- [ ] Refund path (manual via admin for now)

### Events
`checkout_started`, `payment_succeeded`, `payment_failed`

### Edge cases
- [ ] Payment succeeds but the browser closes before the redirect → webhook unlocks; Home shows paid on next open
- [ ] Webhook arrives before the order row commits → retry-safe lookup by `provider_ref`
- [ ] UPI pending for minutes → "We'll confirm in a moment" state; no double charge on retry
- [ ] Refund after recipes exist → project read-only, audio kept until the buyer asks for deletion

**Acceptance:** a new user pays with UPI in Razorpay test mode, completes setup, and the project unlocks; replayed webhooks don't create duplicate orders.

---

## 14. Book and reveal day

Screens: **F2** Family cookbook `/b/<token>` · **R12** Reveal day.

### Build
- [ ] Book compiler: cover (title, cook's name, optional photo), dedication, contents, recipe pages with QR, About the cook, closing page (BOOK-1)
- [ ] Screen PDF (A5/square for phones) (BOOK-2)
- [ ] F2 web book: cover, dedication, "A message from Mummy" slot (QR-11, P1), contents with a play button per recipe, PDF download, "Ask for a dish" (module 12) (completes QR-8)
- [ ] Recipe-card images per recipe for forwarding (BOOK-4)
- [ ] Always ship: on the reveal date compile whatever is approved; unused quota carries into Volume 2 (BOOK-5)
- [ ] R12: cover preview, family-group message (`wa.me`), PDF, Volume 2 offer; scheduled reveal on `reveal_date` or "Reveal now" (BOOK-3)
- [ ] Before reveal, `/b/<token>` shows a "Coming on <date>" page unless the buyer previews while logged in

### Events
`book_compiled`, `book_revealed`, `book_pdf_downloaded`, `book_page_viewed`, `volume2_offer_shown`

### Edge cases
- [ ] Reveal date arrives with 0 approved recipes → no reveal; buyer asked to pick a new date
- [ ] Recipe approved after reveal → added to the web book automatically; PDF recompiled on request
- [ ] `share_pages_as_ready = false` → nothing visible to family until reveal
- [ ] Large books (25 recipes) → PDF compiled in the worker, not the request

**Acceptance:** a 10-recipe project produces a PDF and web book in which every recipe's QR and link play the right voice; reveal on the set date gives the buyer the family message.

---

## 15. Mom's page (optional, P1)

Screens: **C6** Cook's page · **C7** Speaking a recipe · **C8** Her finished page. Open question for Saksham (UX spec §6.1); recommended as P1 because WhatsApp covers P0 and S2 already builds the recorder.

### Build
- [ ] `/m/<token>` (no login, revocable, same rules as listen tokens), Hindi first, opened from a link in the chat
- [ ] C6: big kumkum "रेसिपी बोलिए", progress, family requests each with a mic, her pages, help → calls the buyer
- [ ] C7: S2 recorder with her copy ("गलती हो जाए तो बस दोबारा बोल दीजिए")
- [ ] C8: page preview, "मेरी आवाज़ सुनिए", weekly plays, send to family, next recipe

### Edge cases
- [ ] Link forwarded to someone else → anyone with it can record into her project; buyer sees every clip before approval, can revoke the link
- [ ] Old Android WebView in WhatsApp → falls back to "send a voice note here instead"

---

## 16. Upsell, admin and metrics

- [ ] Volume 2 (+10 recipes) one-tap purchase from Home and reveal (UP-1); price from config
- [ ] Admin: all projects, pipeline failures, stuck projects (> 10 days), WhatsApp delivery errors, refunds (OPS-1)
- [ ] Metrics page from `events` and `listen_events`: activation, completion, median recipes at day 14/30, rescue, voice (non-owner QR plays), family joins, Volume 2, edits per recipe, p90 page-back time (PRD §10)

**Acceptance:** the founder can answer every PRD §10 pilot metric from the admin page without SQL.

---

## 17. Launch readiness

- [ ] Privacy policy and terms (DPDP Act 2023: cook's consent, deletion on request, no training on audio) (§13)
- [ ] Data deletion flow (buyer or cook request → audio, transcripts, pages, events removed)
- [ ] Listen-link permanence policy written down and domain auto-renew on
- [ ] Load check: 50 voice notes at once (Mother's Day spike) within SLA
- [ ] Accessibility pass on listen, book and cook pages on a budget Android phone
- [ ] Cost check: AI + messaging per 10-recipe book ≤ ₹250 on real pilot data (§11)
- [ ] Support playbook: cook stuck, payment failed, QR doesn't scan, recording lost
- [ ] Trademark and domain checked for the final name; `APP_NAME` and `PUBLIC_BASE_URL` set

---

## Later (P1 / P2, not scheduled)

Pull into a module only with evidence from the pilot.

- **P1:** WA-7 commands · WA-8 photos of handwritten recipes (S1 entry exists) · WA-10 / UP-3 Interview Mom for Me · AI-7 book writing assist · AI-8 eval harness in CI · DASH-4 sections and reorder · QR-10 clip editing (trim, pick clips) · QR-11 "message from Mummy" QR · QR-12 audio ZIP export · ENG-6 rescue queue · BOOK-6 themes · BOOK-7 print-ready PDF · UP-2 tier upgrade · BUY-6 Stripe + USD · OPS-2 cost tracking · "We've heard so far" live checklist in S2 · regional languages
- **P2:** BUY-7 gift for someone else · WA-9 chat-export import · UP-4 print-on-demand

---

## Decisions log

Record decisions that change the plan (newest first).

| Date | Decision | Why |
|---|---|---|
| 2026-10-24 | Top 10 digital is ₹1,200 in India and about $22 abroad (nets about ₹2,000); Volume 2 and Family Edition prices still open | Saksham's call in the go-to-market work; PRD §9 and §11 updated |
| 2026-10-25 | Mobile UX v1 approved as the starting point; plan reorganised into modules with data, events and edge cases per module | Saksham's call; build the new UX screen by screen instead of patching the old UI |
| 2026-10-25 | One ordered `dishes` table with `requested_by` replaces the separate `dish_requests` table | The wishlist, family requests and nudges all need the same ordered list |
| 2026-10-25 | Analytics events moved from M7 to an early module | Every module needs to record events from day one to measure the pilot |
| 2026-10-25 | In-app recording (self and assisted) built before WhatsApp | Needs no Meta approval; same recorder serves the escalation "Record together" and the cook's page later |
| 2026-10-25 | Working name **Andaaz**, set by `APP_NAME` | Trademark and domain not checked yet |
| 2026-10-24 | Database: Postgres via SQLAlchemy Core + Alembic; SQLite kept for local runs and tests | Smallest change to the services; schema changes stay safe on live data |
| 2026-10-24 | Structuring on Claude Sonnet 5.5 at `medium` effort; transcription stays on `gpt-4o-transcribe` | Saksham's call; transcription quality across languages matters most |
| 2026-10-24 | Digital-first at ₹999 for 10 recipes; print deferred to P2 | 60% margin after GST; low-risk test of demand |
| 2026-10-24 | QR voice playback is P0 and built right after foundations | The cook's voice is the product's signature |
