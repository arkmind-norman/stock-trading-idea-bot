# Stock Trading Idea Bot — Build & Deployment Plan

## 1. Concept

Friends post stock trade ideas into a **shared Telegram group**. The bot:

1. Watches the group, reads every message, and uses an LLM to detect when a message contains a trade idea — extracting the ticker, direction (long/short), and any target/stop mentioned.
2. Attributes the idea to whoever sent it (their Telegram user ID/username).
3. Opens a simulated paper position at the current market price, tagged to that person.
4. Tracks the position going forward using daily price data.
5. Publishes a **public website** showing each person's all-time simulated performance as a line chart, so everyone can see whose trade ideas actually make money over time.

## 2. Platform: Telegram only

Telegram is the sole channel. Bot token is issued instantly via @BotFather — no business verification, no approval wait, no per-message cost. The bot is added to your friend group as a member and reads messages there (needs "Group Privacy" disabled in @BotFather settings so it can see all messages, not just commands directed at it).

## 3. Architecture

```
┌──────────────────┐      ┌──────────────────┐
│  Telegram Group   │─────▶│  Webhook Ingress  │
│  (friends post     │◀─────│  (FastAPI)        │
│   trade ideas)     │      └────────┬─────────┘
└──────────────────┘                 ▼
                          ┌────────────────────┐
                          │  Idea Detector +     │
                          │  Parser (LLM)        │
                          │  → is this an idea?  │
                          │  → ticker, side,     │
                          │    target/stop       │
                          └────────┬─────────────┘
                                     ▼
                          ┌────────────────────┐
                          │  Simulator Engine    │
                          │  - opens position     │
                          │    tagged to sender   │
                          │  - marks-to-market    │
                          │  - closes on rule     │
                          └────────┬─────────────┘
                                     ▼
                ┌───────────────────────────────────┐
                │  Postgres DB: users, ideas,         │
                │  positions, daily_equity, price_ticks│
                └────────┬────────────────────────────┘
                          ▼                        ▼
              ┌────────────────────┐   ┌────────────────────────┐
              │  Bot replies in     │   │  Public Website         │
              │  group confirming   │   │  - per-person line chart│
              │  the simulated trade│   │  - all-time performance │
              └────────────────────┘   │  - leaderboard ranking   │
                                        └────────────────────────┘
```

A **daily scheduled job** (after US market close) re-prices all open positions, computes each person's daily equity value, and appends one data point per person to a `daily_equity` table — this is what feeds the line charts.

## 4. Component-by-component plan

### 4.1 Telegram ingestion
- Use `python-telegram-bot`, webhook mode (or long-polling for local dev).
- Bot must have Group Privacy **disabled** so it receives all group messages, not just `/commands`.
- Every incoming message → `IncomingMessage {telegram_user_id, username, display_name, text, message_id, timestamp}`.

### 4.2 Idea detection & parsing (LLM-based)
- Not every message is a trade idea — most will be banter. Two-step LLM call:
  1. **Classify:** is this message a trade idea? (yes/no, cheap/fast check)
  2. **Extract** (only if yes): `ticker`, `company_name_guess`, `direction (long/short)`, `target_price` (optional), `stop_price` (optional), `confidence`.
- Validate the extracted ticker against a known symbol list from your market data provider to catch hallucinations.
- If confident: bot replies in-thread, e.g. "📈 Opened simulated LONG on AAPL @ $211.40 for @norman."
- If ambiguous: bot asks for clarification, e.g. "Did you mean AAPL (Apple) or ABT (Abbott)?"

### 4.3 Simulator engine
- On a valid idea: fetch the current/latest close price, open a simulated position with a **fixed notional per idea** (e.g. $1,000) so P&L is comparable across people regardless of price per share.
- Entry price: latest available price at time of message (previous close if market's closed; queue to next open if you want intraday entries later).
- Exit rule (default, since most ideas won't specify one): fixed holding period, e.g. **10 trading days**, unless the user gave a target/stop — then close early if either is hit.
- Daily job marks open positions to market and records the running P&L.
- Data source: **daily close prices** via a free source (Alpha Vantage free tier or `yfinance`) — matches your "daily snapshot" preference and avoids intraday rate-limit headaches.

### 4.4 Per-person attribution & performance
- Every idea and position is tagged with `telegram_user_id`.
- `daily_equity` table: one row per `(user_id, date, cumulative_simulated_equity)` — this is the time series the website charts.
- A user's "all-time performance" = cumulative P&L across every idea they've ever posted, plotted day by day since their first idea.

### 4.5 Public website
- Static or lightly-dynamic site, **no login**, publicly viewable link.
- Home page: leaderboard table (rank, name, all-time P&L, win rate, # of ideas) — click into a person for their individual line chart.
- Each person's page: a line chart (equity curve) from their first idea to today, plus a table of their individual ideas (ticker, direction, entry, exit/current, P&L).
- Rebuilds once a day, right after the daily price-update job runs (static JSON/data file regenerated → charts reflect it on next page load).
- Tech: simple approach is a FastAPI endpoint serving JSON + a single HTML/JS page using Chart.js to render the line charts (matches the no-extra-infra, single-file-friendly approach). Can evolve into the `data:build-dashboard` skill's format later if you want a richer look.

### 4.6 Data model (Postgres)
- `users (id, telegram_user_id, username, display_name, first_idea_at)`
- `ideas (id, user_id, raw_text, ticker, direction, target_price, stop_price, submitted_at, status)`
- `positions (id, idea_id, entry_price, entry_time, exit_price, exit_time, notional, status, pnl)`
- `daily_equity (user_id, date, cumulative_pnl, cumulative_equity)` — feeds the charts directly
- `price_ticks (ticker, price, date)` — daily close cache to avoid re-hitting the API

## 5. Tech stack recommendation

- **Backend:** Python (FastAPI) — Telegram bot library, Claude SDK, and market data libraries all have mature Python support.
- **DB:** Postgres (managed, e.g. Railway/Render/Supabase).
- **Scheduler:** Railway/Render cron job, once daily after market close, running the price-update + daily_equity + leaderboard-refresh script.
- **LLM:** Anthropic API (Claude) for idea classification + extraction.
- **Market data:** Alpha Vantage or `yfinance` for daily close prices (free tier is enough at daily granularity).
- **Frontend:** Single HTML page + Chart.js (CDN) reading a JSON endpoint from the FastAPI backend — no separate frontend framework needed for v1.
- **Hosting:** Railway or Render — one web service (bot webhook + website + JSON API), managed Postgres add-on, one daily cron job. Minimal ops.

## 6. Phased build plan

**Phase 0 — Setup (Day 1)**
- Create Telegram bot via @BotFather, disable Group Privacy, add bot to the friend group.
- Set up Anthropic API key, Alpha Vantage/yfinance access, Railway/Render account, Postgres instance.

**Phase 1 — Core pipeline (Week 1)**
- Build Telegram webhook ingestion.
- Build LLM idea classifier + extractor with ticker validation.
- Build simulator engine: fixed notional sizing, fixed holding-period exit rule.
- Store everything in Postgres.
- Bot replies in-group confirming each simulated trade it opens.

**Phase 2 — Daily tracking & attribution (Week 2)**
- Daily cron: mark-to-market open positions, close positions hitting exit rules, write `daily_equity` rows per person.
- `/leaderboard` and `/myideas` bot commands as a quick in-chat check.

**Phase 3 — Public website (Week 2–3)**
- JSON API: leaderboard + per-person time series.
- Single-page site: leaderboard table + click-through line charts (Chart.js).
- Deploy publicly (no login), share the link with the group.

**Phase 4 — Polish**
- Basic monitoring/logging (e.g. Sentry) for failed price pulls or LLM parse failures.
- Nice-to-haves: win-rate stat, best/worst single idea per person, filter by time range.

## 7. Open decisions you'll need to make as you build

- Fixed notional per idea (e.g. $1,000) — needed so P&L is comparable across people.
- Default exit rule when no target/stop is mentioned (recommend: 10 trading days).
- How to handle multiple ideas on the same ticker from the same person, or the same ticker from different people (each is tracked as its own independent simulated position, most likely).
- Whether shorts are in scope for v1, or long-only to start.
- What counts as "a trade idea" vs. banter — worth tuning the LLM classifier prompt with a few real example messages from your group once the bot's live.

## 8. Next step

Say the word and I'll scaffold the actual code (Telegram bot, LLM classifier/parser prompts, Postgres schema, simulator logic, daily cron script, and the website) in the `bot/`, `simulator/`, `leaderboard/`, and `deployment/` folders already created.
