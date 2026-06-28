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
subscriber a **one-time** invite link and **removes** them when their sub lapses
(it bans then unbans, so a renewing user can rejoin with a fresh link).

**Setup**
1. Create a **private group** (or supergroup).
2. Add your bot and **promote it to admin** with at least:
   *Invite users via link* and *Ban users*.
3. Put the group id in `.env`:
   ```
   CLIENT_GROUP_ID=-1001234567890
   # CLIENT_GROUP_INVITE_TTL=86400   # optional: link expires after N seconds
   ```
4. Restart the worker: `docker compose up -d --force-recreate worker`.

The worker syncs membership **every minute**: new subscribers get invited, lapsed
ones get removed. No payment-flow wiring needed — it's driven purely by
subscription state, so it self-corrects after any missed grant.

> Telegram caveat: the bot can only remove members it can see — keep it an admin.
> The one-time link (`member_limit=1`) can't be shared; each subscriber gets their own.

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
