"""License-protected engine endpoints (stubbed).

Accepts ONLY a short-lived session token (never the raw key), re-checks the
live session, applies per-key rate limiting, and filters results server-side by
the caller's entitlement.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.deps import DbDep, SessionContext, SignedSessionDep
from app.gateway.mock_engine import get_opportunities
from app.gateway.schemas import OpportunitiesResponse
from app.services import entitlements, ratelimit
from app.services.errors import NoActiveSubscription, RateLimited

router = APIRouter(prefix="/v1", tags=["engine"])


@router.get("/opportunities", response_model=OpportunitiesResponse)
async def opportunities(
    ctx: SessionContext = SignedSessionDep,
    db: AsyncSession = DbDep,
) -> OpportunitiesResponse:
    # Entitlement is recomputed server-side (cache-first). Revocation/expiry
    # propagates within the cache TTL even though the token is still unexpired.
    ent = await entitlements.get(db, ctx.key_id)
    if ent is None:
        raise NoActiveSubscription()

    allowed, _remaining = await ratelimit.check(ctx.key_id, ent.rate_limit_per_min)
    if not allowed:
        raise RateLimited()

    items = get_opportunities(ent.max_profitability)
    return OpportunitiesResponse(plan=ent.plan_name, count=len(items), items=items)
