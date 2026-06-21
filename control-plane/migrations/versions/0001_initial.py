"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_blogger", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("referred_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referred_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_concurrent_sessions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_profitability", sa.Numeric(5, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("name", name="uq_plans_name"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("payer_fingerprint", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.UniqueConstraint("external_id", name="uq_payments_external_id"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_external_id", "payments", ["external_id"])
    op.create_index("ix_payments_payer_fingerprint", "payments", ["payer_fingerprint"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_flagged", "api_keys", ["flagged"])

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("first_seen_ip", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_id", "fingerprint", name="uq_device_key_fingerprint"),
    )
    op.create_index("ix_devices_key_id", "devices", ["key_id"])
    op.create_index("ix_devices_fingerprint", "devices", ["fingerprint"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_key_id", "sessions", ["key_id"])
    op.create_index("ix_sessions_device_id", "sessions", ["device_id"])
    op.create_index("ix_sessions_revoked", "sessions", ["revoked"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("referrer_type", sa.String(16), nullable=False, server_default="standard"),
        sa.Column("rate", sa.Numeric(4, 3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),
    )
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])

    op.create_table(
        "commissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Numeric(4, 3), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("payment_id", name="uq_commissions_payment_id"),
    )
    op.create_index("ix_commissions_referrer_user_id", "commissions", ["referrer_user_id"])
    op.create_index("ix_commissions_status", "commissions", ["status"])

    op.create_table(
        "abuse_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["key_id"], ["api_keys.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_abuse_events_user_id", "abuse_events", ["user_id"])
    op.create_index("ix_abuse_events_key_id", "abuse_events", ["key_id"])
    op.create_index("ix_abuse_events_type", "abuse_events", ["type"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(128), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("abuse_events")
    op.drop_table("commissions")
    op.drop_table("referrals")
    op.drop_table("sessions")
    op.drop_table("devices")
    op.drop_table("api_keys")
    op.drop_table("subscriptions")
    op.drop_table("payments")
    op.drop_table("plans")
    op.drop_table("users")
