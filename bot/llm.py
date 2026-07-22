from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic

from db.config import settings

_MODEL = "claude-opus-4-8"
# Accepts: standard US/crypto (1-5 letters), Bursa-style digits+suffix (e.g. 0272.KL),
# or bare digits that resolve_ticker will append .KL to.
_TICKER_RE = re.compile(r"^([A-Z]{1,10}|\d{1,6}(\.[A-Z]{2,4})?)$")
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

# A single message could in principle list many tickers (a watchlist dump) —
# cap how many we'll turn into positions so one message can't spam the chat
# or hammer the price-resolution APIs.
_MAX_IDEAS_PER_MESSAGE = 10

# Pass key explicitly — pydantic-settings reads .env but doesn't set os.environ,
# so the default env-var lookup in AsyncAnthropic() would fail.
_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


@dataclass
class TradeIdea:
    ticker: str
    direction: str          # "long" or "short"
    target_price: float | None
    stop_price: float | None
    confidence: float       # 0.0 – 1.0
    company_name: str | None = None  # clean name for exchange search fallback


_CLASSIFY_SYSTEM = """\
You are a classifier for a stock trading group chat.
Respond YES if the message mentions a specific stock, ETF, or crypto with any \
bullish or bearish sentiment — even casually. This includes: buy/sell signals, \
price targets, stop losses, "to the moon", "looks good", "loading up", "dumping", \
earnings plays, or any positive/negative opinion about a named asset. This also \
includes a bare list of tickers/cashtags with no other commentary — treat that as \
a watchlist-style set of bullish calls.
Respond NO only for pure banter with no specific asset mentioned, or general \
market talk with no ticker or company name.

Respond with exactly one word: YES or NO.
Do not explain your reasoning."""

_EXTRACT_SYSTEM = """\
You are a structured data extractor for stock trade ideas posted in a casual group chat.
A message may mention one ticker or several (e.g. a watchlist-style list of \
cashtags) — extract every distinct trade idea mentioned. Return ONLY a JSON \
array, where each element is an object with these fields:
- ticker: string — your best guess at the official exchange ticker symbol.
  Resolve well-known US/crypto names (e.g. "Apple" → "AAPL", "Netflix" → "NFLX",
  "Bitcoin" → "BTC"). For Malaysian Bursa stocks use the 4-digit code + .KL suffix
  (e.g. "Maybank" → "1155.KL", "Petronas Gas" → "6033.KL"). If you are unsure of
  the exact code, return the company name or abbreviation — the system will search
  for the correct ticker. If genuinely not publicly traded, set ticker to null.
- company_name: string — the clean company or asset name mentioned (e.g. "MI Technovation",
  "Maybank", "Apple", "Bitcoin"). Used as a fallback search query. Never null if a
  company was named.
- direction: "long" or "short", judged per ticker. Default to "long" unless the
  message explicitly uses bearish language (short, sell, puts, dump, crash, drop)
  for that specific ticker. Any positive mention, buy signal, or just naming a
  stock without clear bearish intent → "long".
- target_price: number or null
- stop_price: number or null
- confidence: number 0.0–1.0. Set 0.75 whenever a ticker or company name is clearly
  identifiable, regardless of how casually the idea is expressed. Only go below 0.6
  if the specific stock being discussed is genuinely ambiguous.

If only one trade idea is present, return a one-element array. If none, return [].

Return ONLY the JSON array — no markdown fences, no explanation, no prose before
or after it."""


def _float_or_none(val: object) -> float | None:
    try:
        return float(val) if val is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_trade_idea(item: dict) -> TradeIdea | None:
    raw_ticker = item.get("ticker")
    if raw_ticker is None:
        return None
    ticker = str(raw_ticker).upper().strip()
    if not _TICKER_RE.match(ticker) or ticker in ("NONE", "NULL", "NA", "TBD"):
        return None

    direction = str(item.get("direction", "")).lower()
    if direction not in ("long", "short"):
        return None

    confidence = float(item.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    raw_company = item.get("company_name")
    company_name = str(raw_company).strip() if raw_company else None

    return TradeIdea(
        ticker=ticker,
        direction=direction,
        target_price=_float_or_none(item.get("target_price")),
        stop_price=_float_or_none(item.get("stop_price")),
        confidence=confidence,
        company_name=company_name,
    )


async def classify_and_extract(text: str) -> list[TradeIdea]:
    """
    Two-step LLM call:
    1. Classify: does this message mention any trade idea at all? Returns []
       immediately if not, skipping the extraction call.
    2. Extract: every distinct ticker/direction/target/stop/confidence
       mentioned — a message can list several tickers (e.g. a watchlist dump),
       each becomes its own TradeIdea.
    """
    # ── Step 1: cheap yes/no gate ─────────────────────────────────────────────
    classify_resp = await _client.messages.create(
        model=_MODEL,
        max_tokens=5,
        system=_CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    verdict = classify_resp.content[0].text.strip().upper()
    if verdict != "YES":
        return []

    # ── Step 2: structured extraction ────────────────────────────────────────
    extract_resp = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    raw = extract_resp.content[0].text.strip()

    # The model is instructed to return only a JSON array, but especially for
    # multi-ticker messages it sometimes prepends an explanatory sentence
    # first (e.g. "I can only extract one trade idea per message... here's
    # the first one:") — pull the array out of the response instead of
    # requiring the *entire* response to be valid JSON, which would silently
    # drop the whole message on a JSONDecodeError.
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_ARRAY_RE.search(raw)
        if not match:
            return []
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    if not isinstance(items, list):
        items = [items]  # tolerate a bare object instead of an array

    ideas: list[TradeIdea] = []
    for item in items[:_MAX_IDEAS_PER_MESSAGE]:
        if not isinstance(item, dict):
            continue
        idea = _parse_trade_idea(item)
        if idea is not None:
            ideas.append(idea)
    return ideas
