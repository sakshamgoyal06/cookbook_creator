# PRD: Mom's Cookbook Studio

> **The north star for this project.** When a product, design or engineering decision is unclear, this document decides. If reality proves it wrong, update the document first, then the code.

| | |
|---|---|
| **Product** | Mom's Cookbook Studio (working name) |
| **Document owner** | Product lead |
| **Status** | v1.0, approved direction |
| **Last updated** | 2026-10-24 |
| **Primary market** | India (domestic) first; Indian diaspora (US/UK/CA/AU/Gulf) second |
| **First launch target** | Paid pilot before Mother's Day 2027 (Sunday 9 May 2027) |

---

## 1. One-line summary

**Mom sends recipe voice notes on WhatsApp. The family gets a beautiful digital cookbook in her words, with a QR code on every recipe that plays her actual voice.**

We are not selling an AI recipe formatter. We are selling **family legacy as a gift**: the adult child pays, Mom talks, and the whole family gets something they keep for generations.

---

## 2. Problem

1. **Family recipes are disappearing.** They live in Mom's head as "thoda sa", "andaaza" and "jab tak pak jaye". When she can no longer cook or explain them, they're gone.
2. **Children who moved away can't cook their mother's food.** Indian families are spread across cities and countries. Adult children miss the food and don't know how to make it.
3. **Existing ways of capturing recipes don't fit Indian parents:**
   - Typing is a barrier for many older parents.
   - Apps need installing, logging in and learning.
   - Indian recipes don't fit "1 tsp" templates; they need someone to interpret them.
4. **Existing keepsake products aren't built for this audience.** Storyworth and Remento are US-focused, English-first, general life stories, priced at about $99, and don't handle Hindi/Hinglish, WhatsApp or structured recipes.

---

## 3. Goals and non-goals

### 3.1 Goals (first 12 months)

| # | Goal | How we'll know |
|---|---|---|
| G1 | Prove families will pay for a **digital-first** cookbook experience in India | 50 paid families in the pilot; ≥ 500 paid books in year 1 |
| G2 | Make Mom **actually finish** (the main risk) | ≥ 70% of paid projects reach 10 approved recipes |
| G3 | Preserve Mom's **voice**, not just her recipes | 100% of recipes in a finished book carry a working voice QR; ≥ 50% of finished books get at least one QR play from someone other than the buyer |
| G4 | Run a healthy unit economy at India prices | ≥ 55% contribution margin at ₹999 after GST, payment fees and AI costs |
| G5 | Grow mainly through families sharing | ≥ 30% of new buyers come through referral, family sharing or a shared recipe page |

### 3.2 Non-goals (for now)

- Printed books (P2; planned as an upsell once digital works, see §11).
- General life-story or memoir capture; we stay focused on recipes.
- A native mobile app; WhatsApp plus the mobile web is enough.
- A public recipe marketplace or social feed. Everything is private to the family.
- Cuisines beyond Indian home cooking in v1. The prompt and taste are Indian-first.
- Restaurant or B2B recipe documentation.

---

## 4. Users and personas

### 4.1 The Buyer: "Aarav", 32, Bengaluru (or New Jersey)

- Works in tech. Lives away from his parents and visits 2–3 times a year.
- Misses Mom's rajma and has tried to write it down on calls, without success.
- Wants a meaningful gift for Mother's Day, Mom's 60th, or his sister's wedding.
- **Jobs to be done:** "Help me save Mom's recipes before it's too late, without making her do homework, and give me something beautiful to give the family."
- **Pays.** Sets up the project, follows progress and reviews pages.

### 4.2 The Storyteller: "Sunita ji", 61, Jaipur

- Uses WhatsApp every day: voice notes, forwards, family groups. Rarely types in English.
- Speaks Hindi mixed with English (Hinglish), or a regional language.
- Loves explaining food, and loves being asked.
- **Jobs to be done:** "Let me tell my recipes the way I speak, without learning anything new, and let me see that my children value them."
- **Never pays, never installs, never logs in.**

### 4.3 The Family: siblings, cousins, grandchildren

- Join for free through a link. Request dishes ("Dadi, aloo paratha please!"), see pages as they arrive, and scan QRs to hear her voice.
- The main source of growth: the people who forward the product and the future buyers of upsells.

### 4.4 Later segments (not v1; do not design for them now)

- Wedding and occasion gifting ("Mom's recipes for the new couple").
- Community cookbooks (temples, RWAs, schools, fundraisers).
- Home chefs and creators who want to self-publish (a separate "Creator" tier).
- Diaspora buyers paying in USD (P1, same product, different price).

---

## 5. Market context and positioning

| | **Storyworth** | **Remento** | **Us** |
|---|---|---|---|
| What gets captured | Life stories (mostly written) | Life stories (voice, web recorder) | **Recipes** (voice on WhatsApp) |
| Language | English | English | **Hindi, Hinglish, regional + English** |
| How the parent contributes | Weekly email prompt | Weekly prompt, web recorder | **WhatsApp voice notes, follow-up questions, reminders** |
| Voice in the final book | No | QR plays the voice | **QR plays the voice (P0)** |
| Price | about $99 (plans $59–199 in 2026) | $99 including a hardcover | **₹999 digital** (print later) |
| Proof of the market | Over 1M books printed; profitable | Shark Tank 2025; about $1.5M→$4.6M projected sales | — |

**Positioning:** *"The easiest way to save Mom's recipes in her own voice. She just sends WhatsApp voice notes; you get a cookbook the whole family can hear."*

**Advantages over them:**
1. Recipe-specific AI that keeps her voice and **never invents** quantities.
2. Built for Indian languages.
3. Uses the WhatsApp habit parents already have.
4. Rupee cost base (human help is affordable).
5. Built for families spread across cities and countries.

**Risk:** either competitor could launch a "recipe edition". We defend by going deeper on language and cuisine and by getting more parents to finish (§12).

---

## 6. Product principles

These settle trade-offs. When two of them conflict, the earlier one wins.

1. **Mom never installs, logs in or types.** If a feature needs her to, redesign it.
2. **Her voice is the product.** Keep the original audio for good. Every recipe page links back to her voice.
3. **Never invent; always ask.** The AI may approximate only when it's safe, and every approximation is flagged. Unclear items go back to Mom as a short question, not a guess.
4. **Finishing matters more than perfection.** A finished 10-recipe book beats a perfect, abandoned 30-recipe project. Always ship what exists by the reveal date.
5. **Every page should be worth sharing.** Each recipe Mom finishes becomes a beautiful image she wants to forward.
6. **Private by default.** Nothing is public. Share links are unguessable and can be revoked.
7. **Cheap to run.** AI and messaging cost per book must stay under ₹250 for 10 recipes.

---

## 7. The core experience

```
 BUYER                         STORYTELLER (Mom, on WhatsApp)          FAMILY
 ─────                         ──────────────────────────────          ──────
 1. Buys "Mom's Top 10"   ─┐
 2. Sets up the gift:      │
    Mom's name, number,    │
    language, occasion,    │
    reveal date            │
 3. Sends invite to Mom  ──┴─▶ 4. "Namaste Sunita ji 🙏 Aarav has
    (pre-written message,         started a cookbook of your recipes.
     from his own WhatsApp)       Just send a voice note anytime."
                               5. Sends voice note: "Rajma aise
                                  banate hain…"
                               6. Gets 1–3 quick follow-up questions:
                                  "Thoda sa hing: a pinch or ¼ spoon?"
                               7. Answers by voice
                               8. Gets her finished recipe page as
                                  an image: "Page 3 of 10 done! 🎉" ──▶ 9. Forwards it to family
                                                                          groups
 10. Reviews and approves  ◀── (pages appear on the dashboard)        11. Request dishes, see
     each page                                                            progress (free)
                               12. Gentle reminders if she goes
                                   quiet; escalates to Aarav
 13. Reveal day: the book is unveiled to the whole family ─────────▶ 14. Open the book, scan a
                                                                          QR, hear Mom's voice
 15. Upsell: Volume 2 (+10 recipes), Family Edition, later print
```

### 7.1 Key moments we must get right

| Moment | What "great" looks like |
|---|---|
| **The gift invite** | Mom feels honoured, not assigned homework. The message is in her language and from her child's own number. |
| **First voice note** | Within 72 hours of the invite. Her first page comes back within minutes, not days. |
| **Follow-up questions** | No more than 3 per recipe; short; in her language; answered by voice. They feel like a curious child asking, not a form. |
| **Her page comes back** | It looks like a real cookbook page with her name on it. She wants to forward it. |
| **Going quiet** | Nudges are warm, specific ("Riya is asking for your kadhi 😊") and pass to a person (her child) before they ever feel spammy. |
| **Reveal day** | The family opens the book together. Someone scans a QR, hears her voice, and cries. |

---

## 8. Functional requirements

Priorities:
- **P0:** required for the paid pilot and launch.
- **P1:** soon after launch.
- **P2:** later or by evidence.

### 8.1 Buyer purchase and gift setup

| ID | Requirement | Pri |
|---|---|---|
| BUY-1 | The buyer signs up with email or Google (exists today) and buys a tier before the project starts. | P0 |
| BUY-2 | Razorpay checkout in INR (UPI, cards, netbanking). Payment confirmation unlocks the project. GST-ready invoices. | P0 |
| BUY-3 | Gift setup wizard: Mom's name (how she should be addressed, e.g. "Sunita ji", "Mummy"), her WhatsApp number, preferred language, occasion, **reveal date**, cookbook title, dedication. | P0 |
| BUY-4 | Generate a ready-to-send invite message in Mom's language for the buyer to send from their own WhatsApp (link that opens WhatsApp with the text filled in), plus a printable or shareable gift card image. | P0 |
| BUY-5 | Mom's explicit consent captured on her first interaction (see PRIV-2). | P0 |
| BUY-6 | Stripe checkout and USD pricing for diaspora buyers, chosen by card country or location. | P1 |
| BUY-7 | Gift purchase for someone else (the buyer pays; a sibling runs the project). | P2 |

### 8.2 Storyteller experience (WhatsApp)

| ID | Requirement | Pri |
|---|---|---|
| WA-1 | WhatsApp Business number on the Meta Cloud API. Incoming voice notes, text and photos from a registered storyteller number go to her project. | P0 |
| WA-2 | Each voice note runs through the pipeline: store audio → transcribe → structure → follow-ups → page (§8.3). Mom gets an acknowledgement within 30 seconds ("Got it! Writing it down… 📝"). | P0 |
| WA-3 | **Follow-up questions:** the top unclear items (at most 3) from `unclear_items_for_review` are sent back as short questions in Mom's language. Her voice or text answers are attached to the recipe and it is re-structured. Unanswered questions after 48 hours are left for the buyer to resolve. | P0 |
| WA-4 | **Page comes back:** once a recipe is structured (and any follow-ups resolved or timed out), Mom gets the rendered page as an image, plus progress: "Page 4 of 10 done 🎉". | P0 |
| WA-5 | Handle several voice notes for one recipe: notes within a short window (default 10 minutes), or clearly a continuation ("aur haan…"), are merged into the same recipe. | P0 |
| WA-6 | Language: the bot writes in Mom's chosen language (Hindi, Hinglish or English in P0; regional languages in P1). Short, warm, respectful messages with an emoji or two. | P0 |
| WA-7 | Simple commands Mom can say or type: "next" (what to record next), "stop" (pause reminders), "help" (sends the buyer a call-me request). | P1 |
| WA-8 | Photos Mom sends (the dish, an old handwritten recipe) are attached to the recipe and can appear on its page. | P1 |
| WA-9 | Import past recipe voice notes from an exported WhatsApp chat (the buyer uploads the export). | P2 |
| WA-10 | Phone-call capture: an AI or human interviewer calls Mom at a scheduled time ("Interview Mom for Me" add-on). | P1 |

### 8.3 Recipe pipeline (AI)

| ID | Requirement | Pri |
|---|---|---|
| AI-1 | Transcription of Hindi, Hinglish and English voice notes (`gpt-4o-transcribe` today; evaluate an Indic-language speech-to-text provider on 10 real samples before launch). | P0 |
| AI-2 | Structuring into the existing recipe JSON schema (`prompts/recipe_editor_prompt.txt`). Keeps Mom's warmth and phrases; **never invents ingredients**; flags every approximation. | P0 |
| AI-3 | Structuring on Claude Sonnet 5.5 with structured outputs; robust JSON parsing; no reliance on `content[0]` being text. Models, API keys and base URLs are configurable from `.env`, so a model or provider can be swapped without code changes. | P0 |
| AI-4 | Processing runs **asynchronously** (background worker), never inside the web request. Failures retry with backoff and alert ops, never Mom. | P0 |
| AI-5 | A follow-up question generator turns unclear items into at most 3 natural questions in Mom's language. | P0 |
| AI-6 | Re-structuring merges follow-up answers into the recipe and removes resolved unclear items. | P0 |
| AI-7 | Book-level writing assist: suggests an introduction, "about Mom" and the contents from the recipes; the buyer edits. | P1 |
| AI-8 | Evaluation set: 30 real (consented) voice notes with expected outputs; run before every prompt or model change. | P1 |

### 8.4 Buyer dashboard and review

| ID | Requirement | Pri |
|---|---|---|
| DASH-1 | Project dashboard: progress (x of N recipes), each recipe's status, Mom's last activity, days until reveal. | P0 |
| DASH-2 | Recipe review: view the structured recipe, transcript, audio player and open follow-ups; edit fields with a **form**, not raw JSON; approve. | P0 |
| DASH-3 | Recipe statuses: `received → transcribed → structured → awaiting_mom → needs_review → approved`. | P0 |
| DASH-4 | Reorder recipes and assign them to sections (Breakfast, Dal & Sabzi, Sweets…). | P1 |
| DASH-5 | Buyer can upload audio directly (exists today) as a fallback channel, for example recording Mom in the kitchen. | P0 |

### 8.5 QR voice playback ⭐ (signature feature)

Mom's voice is what turns a recipe PDF into an heirloom. **Every recipe in every book has a QR code that plays her original voice note.** This is P0 and part of the core promise, not an extra.

| ID | Requirement | Pri |
|---|---|---|
| QR-1 | Every recipe page (web, image and PDF) shows a **QR code** plus a **tappable "▶ Listen to Mom" link**. Digital books are mostly read on phones, where a QR on the same screen can't be scanned, so the link is essential. | P0 |
| QR-2 | The QR or link opens a **listen page** (`/l/<token>`): mobile-first, no login, loads fast on 4G. It shows the recipe title, Mom's name, the recording date and a large play button, then plays her voice note(s) in order. | P0 |
| QR-3 | Tokens are random and unguessable (≥ 128 bits, URL-safe), one per recipe. They never expose database IDs. | P0 |
| QR-4 | **Permanent links:** a printed QR can't be updated, so URLs use a domain and path format we commit to keep working long-term. Path format is versioned (`/l/<token>`); never change it without redirects. | P0 |
| QR-5 | Audio files are stored durably in object storage with backups, served through short-lived signed URLs from the listen page. Original audio is **never deleted** while the account is active. | P0 |
| QR-6 | QR rendering for print and screen: error correction level M or higher, at least 2 cm printed, a 4-module quiet zone, dark on light. Tested with the iPhone Camera and Google Lens on screen and on a home-printed page. | P0 |
| QR-7 | The buyer can **revoke or regenerate** a recipe's listen link (old QR stops working; the page says "This recording is private"). | P0 |
| QR-8 | **Book QR** on the cover or dedication page opens the family's cookbook home (all recipes with their voices). | P0 |
| QR-9 | Count plays without personal data. Tell Mom: "Your rajma recording was played 12 times this week ❤️". This also keeps her motivated. | P1 |
| QR-10 | Clip editing: the buyer picks which voice note(s) a QR plays, trims silence, and can add a "story" clip (e.g. where the recipe came from). Basic noise reduction. | P1 |
| QR-11 | A "message from Mom" QR on the dedication page (a short personal voice note recorded for the family). | P1 |
| QR-12 | Audio archive export: the buyer can download all original recordings as a ZIP at any time. | P1 |
| QR-13 | If the service ever shuts down, give every family a full export (book, audio, static listen pages) at least 90 days in advance. | Policy |

**Acceptance test for QR:** print a generated page on a home inkjet printer at 100% scale, scan it with an iPhone camera and with an Android phone using Google Lens, and Mom's voice starts playing within 3 seconds of tapping play on a 4G connection.

### 8.6 Digital cookbook and reveal

| ID | Requirement | Pri |
|---|---|---|
| BOOK-1 | Compile the full digital book: cover (title, Mom's name, optional photo), dedication, contents, recipe pages (each with its QR), "About Mom", closing page. | P0 |
| BOOK-2 | Formats: **screen PDF** (A5 or square for phones) and a **private web cookbook** (`/b/<token>`, mobile-first, every recipe with an inline audio player). | P0 |
| BOOK-3 | **Reveal day:** on the reveal date (or when the buyer chooses), the family gets the book link, with a pre-written WhatsApp message for the buyer to send to family groups. | P0 |
| BOOK-4 | Shareable recipe-card images (one per recipe) for WhatsApp forwarding, including a small QR and branding (this is our marketing). | P0 |
| BOOK-5 | Always ship: if the project reaches the reveal date with fewer recipes than the tier, the book still compiles with what exists, and the remaining quota carries into Volume 2. | P0 |
| BOOK-6 | Several cover and page themes (the database already has `theme`; 5 colour themes exist in config). | P1 |
| BOOK-7 | **Print-ready PDF** (high resolution, bleed, CMYK-safe) as a paid add-on; not included in base tiers. | P1 |

### 8.7 Engagement and finishing

| ID | Requirement | Pri |
|---|---|---|
| ENG-1 | Reminder schedule, per project, adjustable by the buyer: **day 4** without a recipe → gentle nudge to Mom suggesting a specific dish; **day 8** → message the **buyer** ("Mom has gone quiet. Call her, or cook together and record?"); **day 14** → offer Interview Mom for Me. | P0 |
| ENG-2 | Reminders respect quiet hours (9 pm–9 am in Mom's local time) and stop immediately on "stop". | P0 |
| ENG-3 | **Suggested dish list:** the buyer adds 10–15 dishes during setup; reminders and "next" use this list. | P0 |
| ENG-4 | **Family requests:** family members join for free via link and request dishes; Mom sees who asked ("Riya is asking for…"). | P1 |
| ENG-5 | Progress milestones sent to Mom and the buyer (first page, halfway, done). | P0 |
| ENG-6 | Human "rescue" queue for ops: projects stuck for more than 10 days show up for a personal call. | P1 |

### 8.8 Upsells

| ID | Requirement | Pri |
|---|---|---|
| UP-1 | **Volume 2** (+10 recipes) can be bought in one tap from the dashboard and the reveal page. | P0 |
| UP-2 | Upgrade from Top 10 to Family Edition (pay the difference). | P1 |
| UP-3 | Interview Mom for Me (₹499 per call). | P1 |
| UP-4 | Print: softcover and hardcover, ordered by any family member from the reveal page, sent to the nearest printer (India: local print-on-demand; abroad: Lulu or Gelato). | P2 |

### 8.9 Operations and admin

| ID | Requirement | Pri |
|---|---|---|
| OPS-1 | Admin view: all projects, pipeline failures, stuck projects, WhatsApp delivery errors, refunds. | P0 |
| OPS-2 | Cost tracking per project (transcription minutes, AI tokens, WhatsApp messages). | P1 |
| OPS-3 | Basic analytics events for the funnel and the metrics in §10. | P0 |

---

## 9. Pricing and packaging

### 9.1 India (launch)

| Product | Price (incl. GST) | Contents |
|---|---|---|
| **Mom's Top 10, Volume 1** | **₹999** (launch / festive offer ₹799) | 10 recipes, WhatsApp capture, follow-ups, voice QR on every recipe, digital book (PDF + web), family sharing |
| **Volume 2** (+10 recipes) | **₹599** | Adds 10 recipes; new volume or merged edition |
| **Family Edition** | **₹1,999** | 25 recipes, custom theme, "About Mom" writing help |
| **Interview Mom for Me** | **₹499 per call** | A trained Hindi- or regional-language interviewer runs a 45-minute call |
| **Print-ready PDF** | **₹299** | High-resolution file for printing locally |
| *Later:* softcover / hardcover | ₹999 / ₹1,799 | Print-on-demand, shipped within India |

**Pricing rules:**
- Family digital access is **always free**; it drives growth.
- Never include a print-ready file in base tiers, so a future print sale isn't undercut.
- Price as if GST applies even before registration (threshold ₹20 lakh turnover).

### 9.2 Diaspora (P1)

Same product, priced in USD by card country or location:
- Top 10: **$19–29**
- Family Edition: **$49**
- Hardcover (later): about **$59**, extra copies about $35

---

## 10. Success metrics

### 10.1 North-star metric

**Finished books per month**: paid projects that reach their recipe target and are revealed to the family.

### 10.2 Funnel and health metrics

| Stage | Metric | Pilot target |
|---|---|---|
| Acquisition | Landing → paid conversion | ≥ 2% |
| Activation | Mom sends her first recipe within 72 h of the invite | ≥ 70% |
| Engagement | Median recipes per project at day 14 / day 30 | ≥ 4 / ≥ 8 |
| **Completion** | Paid projects reaching 10 approved recipes | **≥ 70%** |
| Rescue | Stalled projects (> 10 days) that resume after an escalation | ≥ 40% |
| Voice | Finished books with a QR play from someone other than the buyer | ≥ 50% |
| Virality | Family members joined per project; buyers coming from shares or referrals | ≥ 3; ≥ 30% |
| Monetisation | Projects buying Volume 2 or Family Edition within 60 days | ≥ 20% |
| Quality | Buyer edits per recipe before approval (lower is better) | ≤ 3 field edits |
| Economics | Contribution margin per ₹999 order | ≥ 55% |
| Speed | Voice note → page back to Mom (p90) | ≤ 5 minutes |

---

## 11. Unit economics (Top 10 at ₹999)

| Line | ₹ |
|---|---|
| Price (incl. GST) | 999 |
| GST at 18% (once registered) | −152 |
| Razorpay fee (~2% + GST) | −24 |
| Transcription (~70 min of audio) | −37 |
| Claude structuring and follow-ups | −62 |
| WhatsApp chat AI | −18 |
| Book-level writing | −18 |
| WhatsApp template messages (~30) | −20 |
| Rendering, storage, QR hosting | −5 |
| Buffer (retries, re-recordings, +30%) | −50 |
| **Contribution** | **≈ 613 (≈ 61% of price; ≈ 72% after GST)** |

- **Fixed costs:** about ₹5–9k a month for hosting, database, storage and email. Break-even at about 10–15 orders a month.
- **Price floor for ≥ 50% margin:** about ₹699.
- **Paid acquisition:** acceptable up to about ₹250–300 per customer.

---

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Mom stops sending recipes** | High | Critical | WhatsApp-only capture; follow-up questions; her page sent back instantly; dish requests from family; reminders that escalate to the child; Interview Mom for Me; always ship what exists (BOOK-5). |
| Poor Hindi/Hinglish transcription | Medium | High | Evaluate an Indic speech-to-text provider on real samples; the buyer can correct the transcript; AI-8 eval set. |
| AI invents or gets quantities wrong | Medium | High | "Never invent" prompt rule; unclear items go back to Mom; the buyer approves every page. |
| Low price makes paid ads unprofitable | High | Medium | Free growth loops (shareable pages, family invites, QR plays); paid ads capped at about ₹300 per customer; upsells raise revenue per customer. |
| WhatsApp policy or template rejections; number banned | Medium | High | Use approved utility templates; send nothing until Mom opts in; respect quiet hours and "stop"; keep upload as a fallback channel. |
| Broken QR links in future | Low | Critical (trust) | Permanent URL commitment (QR-4); domain renewals automated; export policy (QR-13). |
| Voice privacy concerns | Medium | High | Private-by-default unguessable links; revoke and regenerate; explicit consent; DPDP-compliant handling (§13). |
| Competitor launches a recipe edition | Medium | Medium | Go deeper on language and cuisine; WhatsApp; India price point; get there first with families. |
| Seasonal demand spikes | High | Medium | Background processing; ops capacity planned for Mother's Day and Diwali; reveal-date deadlines staggered. |

---

## 13. Non-functional requirements

| Area | Requirement |
|---|---|
| **Privacy and consent** | India's Digital Personal Data Protection Act 2023: Mom is the data principal for her voice, so consent comes from **her** on her first message (in her language), not only from the buyer. A clear privacy notice; data deletion on request; no audio used for model training. |
| **Security** | Every project, recipe and file access checks ownership. Share links are unguessable tokens. Files are never served by guessable filename. Secrets come from the environment. HTTPS only. |
| **Reliability** | Uploaded audio is never lost: write to object storage before processing. Pipeline jobs can be retried safely. Daily database backups. |
| **Performance** | Listen page under 1.5 s first paint on 4G. Mom gets an acknowledgement within 30 s and her page within 5 min (p90). |
| **Accessibility** | Listen and book pages: large type, high contrast, one big play button; usable by a 70-year-old on a budget Android phone. |
| **Localisation** | Bot messages and invite text in Hindi, Hinglish and English (P0); Gujarati, Punjabi, Marathi, Bengali, Tamil, Telugu (P1). |
| **Cost** | AI and messaging cost per 10-recipe book ≤ ₹250, tracked per project (OPS-2). |

---

## 14. Data model (target)

Builds on the existing `users`, `projects` and `recipes` tables.

```
users            (exists)
projects         + storyteller_name, storyteller_phone, storyteller_language,
                   occasion, reveal_date, tier, recipe_quota, payment_status,
                   book_token, consent_at, reminders_paused
recipes          + listen_token, listen_revoked_at, section, approved_at
                   status ∈ received|transcribed|structured|awaiting_mom|needs_review|approved
recipe_audio     id, recipe_id, storage_key, duration_s, kind (original|followup|story),
                 play_order, created_at
recipe_questions id, recipe_id, question_text, answer_text, answer_audio_id,
                 status (open|answered|expired), asked_at, answered_at
family_members   id, project_id, name, phone/email, invite_token, joined_at
dish_requests    id, project_id, family_member_id, dish_name, status
orders           id, project_id, product, amount_paise, currency, provider,
                 provider_ref, status, created_at
wa_messages      id, project_id, direction, template, wa_message_id, status, created_at
listen_events    id, recipe_id, played_at  (no PII)
```

---

## 15. Technical architecture (target)

| Concern | Today | Target (P0) |
|---|---|---|
| Web app | Flask, runs on a laptop | Flask, hosted (Render / Railway / Fly) |
| Database | SQLite | Postgres (managed) |
| File storage | Local `uploads/`, `outputs/` | Object storage (S3 / Cloudflare R2) with signed URLs |
| Processing | Inside the upload request | Background worker (RQ or Celery + Redis) |
| Capture | Web upload only | **WhatsApp Cloud API webhook** + web upload |
| Transcription | OpenAI `gpt-4o-transcribe` | Same, or an Indic speech-to-text provider (decide by eval) |
| Structuring | Claude Sonnet 5.5 (`medium` effort), structured outputs | Same, unless an eval shows a better one; set by `ANTHROPIC_RECIPE_MODEL` |
| Rendering | WeasyPrint, PDF per recipe | WeasyPrint: book PDF, recipe-card PNGs, QR (`segno`) |
| Payments | None | Razorpay (INR); Stripe (USD, P1) |
| Scheduling | None | Worker scheduler for reminders and reveal day |

---

## 16. Release plan

| Phase | When | Scope | Exit criteria |
|---|---|---|---|
| **0: Concierge pilot** | Nov–Dec 2026 | 20–50 paying families at ₹799–999. The founder runs WhatsApp by hand; existing upload, structuring and PDF; QR added by hand or with the first QR-1/2/3 build. | Activation ≥ 70%, completion ≥ 70%, ≥ 5 unprompted "she cried when she heard it" stories |
| **1: P0 MVP** | Jan–Mar 2027 | All P0 requirements above | 100 self-serve paid projects; p90 voice note → page ≤ 5 min; margin ≥ 55% |
| **2: Mother's Day push** | Apr–May 2027 | P1 engagement (family requests, plays shown to Mom, interview add-on), diaspora USD pricing | 500 paid books; ≥ 30% from referrals or shares |
| **3: Print and expansion** | Jun 2027 → | Print-on-demand (India + abroad), regional languages, themes | Print uptake ≥ 20% of finished books |

### 16.1 P0 build order

1. **Foundations:** hosting, Postgres, object storage, background worker; fix the security gaps listed in §17.
2. **QR voice playback:** listen tokens, listen page, QR on recipe pages and in the PDF.
3. **WhatsApp capture:** webhook, storyteller routing, pipeline hook-up, acknowledgements.
4. **Follow-up questions and page sent back to Mom** (image of the page plus progress).
5. **Reminders that escalate** and the suggested dish list.
6. **Payments and gift setup** (Razorpay, wizard, invite message, consent).
7. **Full digital book, web cookbook and reveal day.**
8. **Volume 2 upsell, admin view, analytics events.**

---

## 17. Current codebase: known gaps and tech debt

To fix while building P0:

- **File serving is not access-controlled:** `/outputs/<filename>` serves any PDF to any logged-in user. Move to per-owner checks or signed URLs.
- **Processing is synchronous:** transcription and structuring run inside the upload request, which risks timeouts on long notes. Move to the worker (AI-4).
- **Recipe editing is raw JSON:** `recipe_edit.html` edits ingredients and steps as JSON text areas. Replace with a form (DASH-2).
- ~~**AI parsing is brittle:**~~ Fixed: `structure_recipe` uses structured outputs and reads the text block by type (AI-3). Structuring runs on Claude Sonnet 5.5 and no longer sends `temperature`.
- **Storage:** SQLite and local folders, so it can't run on more than one machine. Move to Postgres and object storage.
- **No tests or CI.** Add pytest for services and routes, plus flake8 in CI.

---

## 18. Open questions

1. Which transcription provider wins for Hindi/Hinglish on cost and quality? Decide using the AI-8 eval set before Phase 1.
2. Should the WhatsApp number be one shared business number, or should each family get a different-looking display name? (Shared to start.)
3. How long do we commit to keep listen links working (10 years? for life?), and how do we price that into the product?
4. Should Volume 2 merge into one combined book or be a separate volume? Test with pilot families.
5. GST registration timing, and invoice requirements for diaspora buyers paying in INR.
6. Do we let family members (not the buyer) pay for upsells and print from the reveal page? (Leaning yes.)

---

## Appendix A: Research references

- Storyworth: [Wikipedia](https://en.wikipedia.org/wiki/Storyworth), [About](https://welcome.storyworth.com/about/), [Pricing 2026 (Memoirji)](https://memoirji.com/blog/storyworth-pricing-2026-buyer-guide/), [Recurring complaints (Yourtale)](https://www.yourtale.art/en/blog/storyworth-reviews)
- Remento: [Wikipedia](https://en.wikipedia.org/wiki/Remento), [Harvard Magazine on Shark Tank](https://www.harvardmagazine.com/index%2ephp/2025/03/harvard-business-school-startup-sharktank-ai), [Keepsake review](https://www.keepsakeproject.co/remento-review-2026)
- Completion is a known pain point: [StoryWorth vs Remento vs Edmund Grey](https://edmundgrey.com/blog/storyworth-vs-remento-vs-edmund-grey/), [How Storyworth works (Keepsake)](https://www.keepsakeproject.co/blog/how-does-storyworth-work)
- Print costs: [Amazon KDP cost formula](https://kdp.amazon.com/en_US/help/topic/GHT976ZKSKUXBB6H), [Lulu POD costs](https://blog.lulu.com/print-on-demand-costs-for-authors/), [POD costs for Indian authors](https://www.goodreads.com/author_blog_posts/26115569-how-much-does-print-on-demand-or-pod-really-cost-for-indian-authors)

Neither Storyworth nor Remento publishes completion rates; Remento's revenue figures are projections reported in Shark Tank coverage. Cost figures in §11 are estimates to check against live vendor pricing before launch.
