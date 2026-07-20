"""
Daily cron job — run once after US market close (e.g. 21:00 UTC).

Steps:
1. Fetch latest close prices for all tickers with open positions.
2. Evaluate exit conditions (target/stop hit, holding period expired).
3. Close positions that have hit their exit rule.
4. Mark remaining open positions to market.
5. Compute each user's cumulative P&L and write one DailyEquity row per user.

TODO: implement each step below.
"""


async def run_daily_job() -> None:
    # TODO: Step 1 — collect all open position tickers and fetch closes
    # TODO: Step 2 — check target/stop/holding-period exit rules
    # TODO: Step 3 — close positions that triggered an exit
    # TODO: Step 4 — mark-to-market remaining open positions
    # TODO: Step 5 — upsert DailyEquity rows for all active users
    raise NotImplementedError


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_daily_job())
