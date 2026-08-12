"""Import every model so `Base.metadata` is fully populated for Alembic."""

from app.core.db import Base
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.bot_content import BotContent
from app.models.device import Device
from app.models.feedback import Feedback
from app.models.notion_sync import NotionSync
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.promo_code import PromoCode, PromoRedemption
from app.models.referral import Commission, Referral
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User

__all__ = [
    "Base",
    "AbuseEvent",
    "ApiKey",
    "AuditLog",
    "BotContent",
    "Device",
    "Feedback",
    "NotionSync",
    "Payment",
    "Plan",
    "PromoCode",
    "PromoRedemption",
    "Commission",
    "Referral",
    "Session",
    "Subscription",
    "User",
]
