from dataclasses import dataclass


@dataclass
class TradeIdea:
    ticker: str
    direction: str          # "long" or "short"
    target_price: float | None
    stop_price: float | None
    confidence: float       # 0.0 – 1.0


async def classify_and_extract(text: str) -> TradeIdea | None:
    """
    Two-step LLM call:
    1. Classify: is this message a trade idea? Returns None if not.
    2. Extract: ticker, direction, target/stop, confidence.

    TODO:
    - Initialise an anthropic.AsyncAnthropic() client using ANTHROPIC_API_KEY
    - Step 1 prompt: simple yes/no classification (cheap, fast)
    - Step 2 prompt: structured extraction (only when step 1 is "yes")
    - Validate the returned ticker against a known-symbols list
    """
    raise NotImplementedError
