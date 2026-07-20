# Stock Trading Idea Bot

A Telegram bot that detects trade ideas from group messages, tracks simulated paper positions, and publishes a public leaderboard showing each person's all-time performance.

See [docs/PLAN.md](docs/PLAN.md) for the full architecture and build plan.

---

## Prerequisites

- Python 3.12+
- PostgreSQL (local or managed via Railway/Render/Supabase)
- A Telegram bot token from [@BotFather](https://t.me/BotFather) (disable Group Privacy so the bot sees all messages)
- An Anthropic API key

---

## Local setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd stock-trading-idea-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL
```

Key variables:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key for idea classification & extraction |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `DATABASE_URL` | Postgres connection string (`postgresql+asyncpg://user:pw@host/db`) |
| `TELEGRAM_MODE` | `polling` for local dev, `webhook` in production |
| `POSITION_NOTIONAL` | Fixed USD notional per simulated trade (default `1000`) |
| `DEFAULT_HOLDING_DAYS` | Days before auto-closing a position (default `10`) |

### 3. Create the database

```bash
# Make sure Postgres is running locally, then:
createdb stockbot
```

The app will auto-create tables on first start (via SQLAlchemy `create_all`).
Before going to production, generate proper Alembic migrations instead.

### 4. Run the server

```bash
uvicorn main:app --reload
```

The server starts on `http://localhost:8000`.

- **Health check:** `GET /health`
- **Leaderboard site:** `http://localhost:8000/leaderboard/`
- **Leaderboard JSON:** `GET /leaderboard/data/leaderboard`
- **User data JSON:** `GET /leaderboard/data/user/{telegram_user_id}`
- **Telegram webhook:** `POST /bot/webhook`

### 5. Start the Telegram bot (long-polling for local dev)

With `TELEGRAM_MODE=polling` set in `.env`, the bot will poll Telegram for updates instead of waiting for webhook deliveries — no public URL needed locally.

> Long-polling support will be wired into the bot startup in Phase 1. For now, the webhook endpoint is stubbed.

### 6. Run the daily job manually

```bash
python simulator/daily_job.py
```

In production this runs as a scheduled cron job at 21:00 UTC Mon–Fri.

---

## Project layout

```
.
├── main.py                  # FastAPI app entry point
├── requirements.txt
├── .env.example
│
├── db/
│   ├── config.py            # Pydantic settings (reads .env)
│   ├── database.py          # Async SQLAlchemy engine + session
│   └── models.py            # ORM models: User, Idea, Position, DailyEquity, PriceTick
│
├── bot/
│   ├── webhook.py           # POST /bot/webhook — Telegram update ingestion
│   ├── handlers.py          # IncomingMessage → trade-idea pipeline
│   ├── llm.py               # LLM classifier + extractor (Anthropic)
│   └── commands.py          # /leaderboard and /myideas bot commands
│
├── simulator/
│   ├── engine.py            # open_position / close_position
│   ├── market_data.py       # Price fetching (yfinance + price_ticks cache)
│   └── daily_job.py         # Daily mark-to-market + DailyEquity writes
│
├── leaderboard/
│   ├── api.py               # FastAPI router: JSON endpoints + HTML serve
│   └── static/
│       └── index.html       # Single-page leaderboard + Chart.js equity curves
│
└── deployment/
    ├── Dockerfile
    └── railway.toml         # Railway web service + daily cron job config
```

---

## Deployment (Railway)

1. Push this repo to GitHub.
2. Create a new Railway project → **Deploy from GitHub repo**.
3. Add a **Postgres** plugin (Railway managed).
4. Set environment variables in Railway's dashboard (same as `.env`).
5. Set `TELEGRAM_MODE=webhook` and `WEBHOOK_URL=https://<your-app>.railway.app`.
6. After deploy, call `GET https://<your-app>.railway.app/bot/set-webhook` once to register the webhook with Telegram.
7. The `railway.toml` configures a daily cron service that runs `simulator/daily_job.py` Mon–Fri at 21:00 UTC.
