"""Stub for the (not-yet-built) product engine.

Returns mock arbitrage opportunities. The ONLY real logic here is server-side
entitlement filtering: trial keys (max_profitability cap) see only the low-tier
opportunities; paid keys see everything. The client cannot influence this — it
asks, the server decides what to return.
"""

from __future__ import annotations

from app.gateway.schemas import Opportunity

# Static sample book spanning low- and high-profitability tiers.
_BOOK: list[Opportunity] = [
    Opportunity(id="op-001", market="binance/kraken", pair="BTC/USDT", profitability=0.008, notional_usd=5000),
    Opportunity(id="op-002", market="okx/bybit", pair="ETH/USDT", profitability=0.015, notional_usd=3000),
    Opportunity(id="op-003", market="kraken/coinbase", pair="SOL/USDT", profitability=0.020, notional_usd=2000),
    Opportunity(id="op-004", market="bybit/binance", pair="XRP/USDT", profitability=0.034, notional_usd=1500),
    Opportunity(id="op-005", market="coinbase/okx", pair="BTC/USDT", profitability=0.052, notional_usd=8000),
    Opportunity(id="op-006", market="gate/mexc", pair="ARB/USDT", profitability=0.071, notional_usd=1200),
]


def get_opportunities(max_profitability: float | None) -> list[Opportunity]:
    """Trial cap filters to the low-profitability tier; None returns all."""
    if max_profitability is None:
        return list(_BOOK)
    return [op for op in _BOOK if op.profitability <= max_profitability]
