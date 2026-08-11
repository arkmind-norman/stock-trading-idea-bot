"""Unit tests for bot.llm.classify_and_extract.

All Anthropic API calls are mocked so no network access is required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.llm import TradeIdea, classify_and_extract


def _make_response(text: str) -> MagicMock:
    """Build a fake anthropic Message response with a single TextBlock."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _item(**kwargs) -> dict:
    defaults = {
        "ticker": "AAPL",
        "direction": "long",
        "target_price": None,
        "stop_price": None,
        "confidence": 0.9,
    }
    defaults.update(kwargs)
    return defaults


def _extract_payload(*items: dict) -> str:
    """Convenience: build the JSON array string the extraction step should return."""
    return json.dumps(list(items) or [_item()])


@pytest.mark.asyncio
async def test_non_trade_idea_returns_empty_list():
    """When the classifier says NO, the function returns [] immediately."""
    classify_resp = _make_response("NO")
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=classify_resp)
        result = await classify_and_extract("lol what did you have for lunch")
    assert result == []
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_basic_long_idea_extracted():
    """A clear long trade idea is parsed into a one-element TradeIdea list."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(_item(
        ticker="AAPL",
        direction="long",
        target_price=230.0,
        stop_price=195.0,
        confidence=0.95,
    )))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("I'm buying AAPL here, target 230, stop 195")

    assert len(result) == 1
    idea = result[0]
    assert isinstance(idea, TradeIdea)
    assert idea.ticker == "AAPL"
    assert idea.direction == "long"
    assert idea.target_price == pytest.approx(230.0)
    assert idea.stop_price == pytest.approx(195.0)
    assert idea.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_short_idea_no_targets():
    """A short idea without target/stop prices is parsed correctly."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(_item(
        ticker="TSLA",
        direction="short",
        target_price=None,
        stop_price=None,
        confidence=0.7,
    )))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("shorting TSLA")

    assert len(result) == 1
    idea = result[0]
    assert idea.ticker == "TSLA"
    assert idea.direction == "short"
    assert idea.target_price is None
    assert idea.stop_price is None


@pytest.mark.asyncio
async def test_invalid_ticker_dropped():
    """An item with a non-alphabetic or too-long ticker is dropped."""
    classify_resp = _make_response("YES")
    # Ticker with digits — should fail the _TICKER_RE check
    extract_resp = _make_response(_extract_payload(_item(ticker="AA123")))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("buy AA123")
    assert result == []


@pytest.mark.asyncio
async def test_invalid_direction_dropped():
    """An item with an unrecognised direction is dropped."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(_item(direction="buy")))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("buy some AAPL")
    assert result == []


@pytest.mark.asyncio
async def test_malformed_json_returns_empty_list():
    """If the extraction step returns non-JSON with no recoverable array, [] is returned."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response("Sorry, I cannot extract that.")
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("buy NVDA")
    assert result == []


@pytest.mark.asyncio
async def test_json_array_recovered_despite_preamble_text():
    """
    Regression test: for multi-ticker messages the model sometimes prepends
    an explanation before the JSON array (e.g. "I can only extract one trade
    idea per message... here it is:") instead of returning pure JSON. The
    array should still be recovered rather than the whole message being
    silently dropped.
    """
    classify_resp = _make_response("YES")
    payload = _extract_payload(_item(ticker="DRAM", confidence=0.75))
    prefixed = (
        "I can only extract one trade idea per message, but this message "
        f"contains multiple tickers. I'll extract the first one:\n\n{payload}"
    )
    extract_resp = _make_response(prefixed)
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("$DRAM\n\n$ONDS\n\n$NOW\n\n$PLTR")

    assert len(result) == 1
    assert result[0].ticker == "DRAM"


@pytest.mark.asyncio
async def test_multiple_tickers_all_extracted():
    """A watchlist-style message with several tickers extracts one TradeIdea each."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(
        _item(ticker="DRAM", confidence=0.75),
        _item(ticker="ONDS", confidence=0.75),
        _item(ticker="PLTR", confidence=0.75),
    ))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("$DRAM\n\n$ONDS\n\n$PLTR")

    assert [idea.ticker for idea in result] == ["DRAM", "ONDS", "PLTR"]


@pytest.mark.asyncio
async def test_confidence_clamped_to_unit_interval():
    """Confidence values outside [0, 1] are clamped."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(_item(confidence=1.8)))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("long NVDA")
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_classify_step_only_called_once_on_no():
    """When classify says NO, we must NOT make a second API call."""
    classify_resp = _make_response("NO")
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=classify_resp)
        await classify_and_extract("hey everyone what's up")
    assert mock_client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_two_calls_made_for_trade_idea():
    """A valid trade idea triggers exactly two API calls."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload())
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        await classify_and_extract("long AAPL here")
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_ticker_lowercased_in_extraction_is_uppercased():
    """Lowercase tickers returned by the LLM are normalised to uppercase."""
    classify_resp = _make_response("YES")
    extract_resp = _make_response(_extract_payload(_item(ticker="msft")))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("long msft")
    assert len(result) == 1
    assert result[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_ideas_beyond_cap_are_dropped():
    """More than _MAX_IDEAS_PER_MESSAGE items are truncated, not all dropped."""
    classify_resp = _make_response("YES")
    items = [_item(ticker=chr(65 + i), confidence=0.75) for i in range(15)]
    extract_resp = _make_response(_extract_payload(*items))
    with patch("bot.llm._client") as mock_client:
        mock_client.messages.create = AsyncMock(
            side_effect=[classify_resp, extract_resp]
        )
        result = await classify_and_extract("watchlist dump")
    assert len(result) == 10
