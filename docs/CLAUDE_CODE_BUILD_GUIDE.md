# Building the Trade Idea Bot with Claude Code — Zero to Deployed

This is your step-by-step action plan for building the whole project (Telegram bot → simulator → public leaderboard website) using **Claude Code** as your builder. At each step you'll see: what account/tool to set up (if any), and the exact prompt to give Claude Code. You review and approve what it does; you don't need to write code by hand.

Reference: the full architecture and design decisions live in `docs/PLAN.md` in this same project folder — Claude Code should read that file first in Step 2.

---

## Phase 0 — Accounts & tools (do this before opening Claude Code)

You need five things set up. None of these require coding — just signing up.

1. **Anthropic Console account + API key** (for the LLM that reads trade ideas)
   - Go to console.anthropic.com, sign up, add a payment method, create an API key. Save it somewhere safe — you'll paste it into an `.env` file later, never into chat.

2. **Telegram bot token**
   - Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts (choose a name and a username ending in `bot`).
   - BotFather gives you a token like `123456:ABC-DEF...`. Save it.
   - Still in the BotFather chat, send `/setprivacy`, pick your bot, choose **Disable** — this lets the bot read every message in your group, not just commands.

3. **GitHub account + empty repo**
   - Create a free repo, e.g. `stock-trading-idea-bot`. Claude Code will push code here.

4. **Hosting account: Railway (recommended) or Render**
   - Sign up at railway.app (or render.com). Free/trial tier is enough to start. You'll connect this to your GitHub repo later so it auto-deploys.

5. **Claude Code installed on your machine**
   - Requires Node.js 18+ and a Claude Pro/Max/Team/Enterprise account (the free Claude.ai plan doesn't include Claude Code).
   - Install: `npm install -g @anthropic-ai/claude-code` (or the native installer for your OS).
   - Run `claude` from your project folder — it opens a browser window to sign in and authorize, done in under 5 minutes.

Once you have: Anthropic API key, Telegram bot token, GitHub repo URL, and a hosting account — you're ready for Phase 1.

---

## Phase 1 — Kick off the project in Claude Code

1. Open a terminal, `cd` into this project folder (`stock-trading-idea-bot`), and run:
   ```
   claude
   ```
2. First prompt to Claude Code:
   > "Read docs/PLAN.md in this folder — that's the design for the project we're building. Set up a Python FastAPI project structure inside the existing bot/, simulator/, leaderboard/, and deployment/ folders, with a requirements.txt, a .env.example file listing the env vars we'll need (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL), and a README explaining how to run it locally. Don't write business logic yet — just scaffolding."
3. Review what it creates. Ask questions if anything's unclear — Claude Code will explain its choices if you ask.
4. Create a real `.env` file (not committed to git) and paste in your actual Anthropic API key and Telegram bot token.
5. Prompt:
   > "Initialize this as a git repo, add a .gitignore that excludes .env and __pycache__, and push it to [your GitHub repo URL]."

---

## Phase 2 — Database schema

1. Prompt:
   > "Set up a Postgres schema using the data model in section 4.6 / 6 of docs/PLAN.md: users, ideas, positions, daily_equity, price_ticks. Use SQLAlchemy models plus Alembic for migrations. Generate the initial migration."
2. For local testing, ask Claude Code to help you spin up a local Postgres (e.g. via Docker) or connect directly to a free Postgres instance from Railway/Supabase — whichever you set up in Phase 0.
   > "Help me connect this to a Postgres instance — walk me through getting a connection string from Railway and putting it in my .env as DATABASE_URL, then run the migration."

---

## Phase 3 — Telegram ingestion

1. Prompt:
   > "Build the Telegram webhook ingestion described in section 4.1 of docs/PLAN.md using python-telegram-bot. For now, just log every incoming group message (sender, text, timestamp) to confirm we're receiving them — don't process trade ideas yet."
2. Test locally: Claude Code can set this up with polling mode first (no public URL needed) so you can verify in your terminal that messages from your Telegram group are coming through.
   > "Run this locally in polling mode so I can test it by sending messages in my Telegram group."

---

## Phase 4 — Idea detection & parsing (LLM)

1. Prompt:
   > "Build the two-step LLM idea classifier and extractor from section 4.2 of docs/PLAN.md, using the Anthropic API. Step 1: classify whether a message is a trade idea. Step 2: if yes, extract ticker, direction, target_price, stop_price, confidence as structured JSON. Write a few unit tests with example messages (both real trade ideas and banter) so we can verify the classifier works before wiring it to Telegram."
2. Run the tests, read through some real example messages from your group chat and feed them in to sanity-check accuracy.
   > "Here are 10 real messages from my group chat: [paste them]. Run the classifier/extractor against each and show me the output so I can check it's working correctly."
3. Tune based on what you see — tell Claude Code specifically what it got wrong and ask it to adjust the prompt.

---

## Phase 5 — Simulator engine

1. Prompt:
   > "Build the simulator engine from section 4.3 of docs/PLAN.md: on a valid idea, open a simulated position with a fixed $[your chosen amount] notional at the latest close price, tagged to the sender. Default exit rule: close after [your chosen number] trading days, or earlier if a target/stop was specified. Use [Alpha Vantage / yfinance] for daily close prices — write a small wrapper module for fetching prices so we can swap providers later if needed."
   - Decide before this step: fixed notional per idea (e.g. $1,000) and default holding period (e.g. 10 trading days) — these were flagged as open decisions in the plan.
2. Prompt:
   > "Write a daily job script that marks all open positions to market, closes any that hit their exit rule, and writes one daily_equity row per user. Add unit tests using fake price data so we can verify P&L math is correct without hitting the real API."
3. Review the test output carefully here — this is the core logic that determines whether your leaderboard numbers are trustworthy. Ask Claude Code to walk you through the P&L calculation on one example if anything looks off.

---

## Phase 6 — Wire it all together end-to-end

1. Prompt:
   > "Now connect the pieces: incoming Telegram message → idea classifier/extractor → if valid, open a simulated position → bot replies in the group confirming the trade with ticker, direction, and entry price. Add the /leaderboard and /myideas bot commands from section 6, Phase 2 of docs/PLAN.md."
2. Test in your live Telegram group (still running locally in polling mode): post a few real trade ideas and banter messages, confirm the bot responds correctly only to real ideas.

---

## Phase 7 — Public website

1. Prompt:
   > "Build the public website from section 4.5 of docs/PLAN.md: a FastAPI JSON endpoint serving the leaderboard and each person's daily_equity time series, and a single static HTML page using Chart.js (via CDN) that shows the leaderboard table plus click-through to each person's all-time line chart. No login required."
2. Open it locally (`http://localhost:8000` or similar) and check the chart renders correctly with your test data.

---

## Phase 8 — Deploy

1. Prompt:
   > "Prepare this project for deployment to Railway: add a Procfile or railway.json, make sure DATABASE_URL and other env vars are read correctly in production, and set up the daily cron job to run the mark-to-market script once a day after US market close (4:30pm ET)."
2. In the Railway dashboard: connect your GitHub repo, add the Postgres plugin, paste in your environment variables (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL is often auto-provided), deploy.
3. Switch the Telegram bot from polling to webhook mode pointing at your new public Railway URL:
   > "Switch the bot from polling to webhook mode now that we have a public URL, and show me the Telegram API call to register the webhook."
4. Add the bot to your real friend group (if it isn't already), and share the website link.

---

## Phase 9 — Verify before trusting the leaderboard

Before you tell your friends "this is live," do a manual check:
- Post 2-3 test trade ideas yourself, wait for the next daily job to run, and manually verify the P&L math against the actual stock price move.
- Check the website chart matches what's in the database.
- Ask Claude Code:
  > "Walk me through the full trail for [ticker], from the original message to the final P&L number shown on the website, so I can confirm nothing's being miscalculated."

---

## Ongoing: iterating with Claude Code

Once live, treat every tweak as a new prompt — e.g. "add a win-rate column to the leaderboard," "the classifier is misfiring on messages that mention a stock without proposing a trade, here are 5 examples, fix it," "add a filter to view last 30 days only." Claude Code keeps context of the codebase across a session, so point it at specific files/sections of docs/PLAN.md rather than re-explaining the whole project each time.

Sources: [Claude Code setup docs](https://code.claude.com/docs/en/setup), [NxCode install guide 2026](https://www.nxcode.io/resources/news/install-claude-code-setup-guide-2026)
