# Connect Notion (advanced database / CRM dashboard)

Turn your bot's data into a real Notion workspace — **Customers, Payments,
Subscriptions, Referrals, Commissions, Flags** — all linked together and updated
automatically. ~5 minutes, no coding.

The bot **creates the databases for you**. You only need to (1) make an
integration, (2) give it a page to work in, and (3) paste two values into `.env`.

---

## 1. Create a Notion integration (get your key)

1. Go to <https://www.notion.so/my-integrations> → **New integration**.
2. Name it (e.g. "Arbitrage CRM"), pick your workspace, **Submit**.
3. Copy the **Internal Integration Secret** — it looks like `ntn_...` or
   `secret_...`. This is your `NOTION_API_KEY`.

## 2. Make a parent page and share it

1. In Notion, create a new blank page (e.g. "CRM"). This is where your databases
   will live.
2. Open the page → click **•••** (top-right) → **Connections** → **Connect to** →
   choose the integration you just made.
   (Without this step the bot can't write to the page.)
3. Copy the page's **id** from its URL. The URL looks like:

   ```
   https://www.notion.so/My-CRM-1234567890abcdef1234567890abcdef
                                  └──────────────┬───────────────┘
                                     this 32-char id is NOTION_PARENT_PAGE_ID
   ```

   Copy the 32-character hex string at the end (after the last `-`). Dashes are
   optional — both forms work.

## 3. Put the values in `.env`

```dotenv
NOTION_SYNC_ENABLED=true
NOTION_API_KEY=ntn_your_secret_here
NOTION_PARENT_PAGE_ID=1234567890abcdef1234567890abcdef
```

Restart so the worker picks it up:

```bash
docker compose up -d            # local
# or, on the VPS (production overlay):
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

## 4. Watch it appear

- Within a few minutes the six databases show up under your parent page, filling
  with rows. To trigger it immediately, send **`/notion sync`** to the bot (admin
  only).
- **`/notion`** shows status and clickable links to each database.

That's it. From now on the worker keeps Notion in sync every few minutes.

---

## What you get

| Database | Rows | Key fields |
|----------|------|-----------|
| **Customers** | one per user | plan, expiry, API-key prefix, devices, risk, language, referrals, earnings |
| **Payments** | one per invoice | amount, currency, provider, status, → Customer |
| **Subscriptions** | one per subscription | plan, status, started/expires, → Customer |
| **Referrals** | one per invite | type, rate, status, → Referrer & Referred |
| **Commissions** | one per reward | amount, rate, status, → Referrer & Payment |
| **Flags & Abuse** | one per event | type, detail, → Customer |

Because the child databases relate back to **Customers**, you can open any
customer and see all their payments, subscriptions and flags in one place, build
filtered views ("expiring this week", "flagged"), and chart revenue — all in
Notion.

## Notes & troubleshooting

- **It's one-way.** Notion is a mirror/dashboard; editing a row in Notion does
  **not** change the product (access is always decided server-side). The next
  sync overwrites manual edits to synced fields.
- **Nothing showed up** → check `/notion` (admin). If it says off, re-check the
  three `.env` values and that you restarted. If on but empty, confirm you added
  the integration under the page's **Connections** (step 2.2).
- **"could not set / create database" in worker logs** → the integration isn't
  connected to the page, or the page id is wrong.
- **Turn it off** anytime: `NOTION_SYNC_ENABLED=false` (or `NOTION_API_KEY=CHANGE_ME`)
  and restart. Your Notion data stays; syncing just stops.
- **Privacy:** only the data already in your database is sent to Notion. Full API
  keys are never stored or synced — only the short non-secret prefix.
