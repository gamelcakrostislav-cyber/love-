"""Pydantic request/response models for the gateway API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    api_key: str = Field(..., min_length=10)
    device_fingerprint: str = Field(..., min_length=8, max_length=128)
    context: dict | None = None


class SessionResponse(BaseModel):
    token: str
    session_id: str
    expires_at: datetime
    plan: str
    rate_limit_per_min: int
    # None => no cap (all opportunities visible).
    max_profitability: float | None
    evicted_sessions: int


class Opportunity(BaseModel):
    id: str
    market: str
    pair: str
    profitability: float  # fractional, e.g. 0.018 == 1.8%
    notional_usd: float


class OpportunitiesResponse(BaseModel):
    plan: str
    count: int
    items: list[Opportunity]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
