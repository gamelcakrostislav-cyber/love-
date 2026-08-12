# Community channels: subscriber group + feedback inbox

Two optional, config-driven channels. Both just need the bot added to a chat and
the chat id in `.env`.

## How to get a chat id

1. Create the group/channel in Telegram.
2. Add **your bot** to it.
3. To read the id: temporarily add **@RawDataBot** (or @getidsbot) to the chat —
   it prints the chat id — then remove it. Supergroup/channel ids look like
   `-1001234567890` (note the leading `-100`).

---

## 1. Exclusive subscriber group

A private group only paying subscribers can be in. The bot DMs each active
subscriber a **join-request** invite link and **approves the join only if they
have an active subscription**; it **removes** (bans then unbans) anyone whose sub
lapses, so a renewing user can rejoin.

Why join-request and not a one-time link: Telegram's `member_limit` caps how
*many* people use a link, not *who* — a forwarded link would let the first
stranger in. With `creates_join_request=True` the bot vets every joiner, so a
leaked link is useless to a non-subscriber.

**Setup**
1. Create a **private group** (or supergroup).
2. Add your bot and **promote it to admin** with at least:
   *Add users* / *Invite users via link*, and *Ban users*.
3. Put the group id in `.env`:
   ```
   CLIENT_GROUP_ID=-1001234567890
   # CLIENT_GROUP_INVITE_TTL=86400      # optional: link expires after N seconds
   # CLIENT_GROUP_INVITE_COOLDOWN=3600  # wait before re-inviting an un-joined subscriber
   ```
4. Restart both services so the worker sweep and the bot's join handler load:
   `docker compose up -d --force-recreate worker bot`.

The worker syncs membership **every minute**: active subscribers who aren't in the
group get a join-request link DM'd (re-tried after the cooldown if undelivered),
and lapsed members get removed. Membership truth is the real group roster — the
bot flips it on the actual join/leave event, not when a link is sent — so a missed
DM or a voluntary leave self-corrects. No payment-flow wiring needed.

> Telegram caveat: the bot must stay an admin — it can only approve joins, see
> members, and remove them while it holds those rights.

---

## 2. Feedback inbox

Routes everything users submit via **💬 Feedback** to one place instead of DMing
every admin.

**Setup**
1. Create a private **group or channel** for feedback.
2. Add your bot (admin of a channel, or member of a group with send rights).
3. Put the id in `.env`:
   ```
   FEEDBACK_CHANNEL_ID=-1001234567890
   ```
4. Restart the bot: `docker compose up -d --force-recreate bot`.

Now each suggestion is posted there (user text is HTML-escaped) and still stored
in the DB (`/feedback` lists the latest). Leave `FEEDBACK_CHANNEL_ID=0` to keep
the old behaviour (DM each admin).

> Want feedback mirrored into a **Notion** database instead/as well? That's a
> follow-up on the existing Notion sync — ask and it can be added.
