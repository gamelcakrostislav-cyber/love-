# 🚀 Quick Start (Mac) — run the bot in 10 minutes

This is the simplest way to run and test your Telegram bot on a Mac.
Follow the steps in order. After each step there's what you should see. ✅

---

## Step 1 — Install Docker Desktop

Docker is the program that runs everything for you.

1. Go to **https://www.docker.com/products/docker-desktop/**
2. Click **Download for Mac** (pick **Apple chip** or **Intel chip** — if unsure,
   click the Apple menu  → *About This Mac*; if it says "Apple M1/M2/M3" choose
   Apple chip).
3. Open the downloaded file and drag **Docker** into **Applications**.
4. Open **Docker** from Applications. Wait until the little **whale icon** 🐳 at
   the top of your screen stops moving.

✅ When the whale is steady, Docker is ready.

---

## Step 2 — Get the project onto your Mac

1. Open the project page on GitHub.
2. Click the green **`Code`** button → **Download ZIP**.
3. Open the downloaded ZIP (it unzips into a folder, e.g. `love-` in your
   **Downloads**).

✅ You now have a folder called `love-` with a `control-plane` folder inside it.

---

## Step 3 — Open Terminal in the project folder

1. Press **Cmd + Space**, type **Terminal**, press **Enter**.
2. Type `cd ` (with a space), then **drag the `control-plane` folder** from Finder
   onto the Terminal window, then press **Enter**.

It will look something like:
```bash
cd ~/Downloads/love-/control-plane
```

✅ Terminal is now "inside" the project.

---

## Step 4 — Create your settings file (`.env`)

Copy this whole block, paste it into Terminal, press **Enter**. It creates the
settings file:

```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql+asyncpg://control:control@postgres:5432/control_plane
REDIS_URL=redis://redis:6379/0
JWT_SECRET=PASTE_A_LONG_RANDOM_STRING
JWT_TTL_SECONDS=900
REQUEST_SIGNING_REQUIRED=true
BOT_TOKEN=PASTE_BOT_TOKEN
ADMIN_IDS=PASTE_YOUR_TELEGRAM_ID
CRYPTOPAY_API_TOKEN=CHANGE_ME
EOF
```

Now fill in the 3 values. Open the file with TextEdit:
```bash
open -e .env
```
- **BOT_TOKEN** — from **@BotFather** in Telegram (`/newbot`, or `/token` for an
  existing bot). Looks like `123456789:AAH....`
- **ADMIN_IDS** — your own Telegram number, from **@userinfobot** (it replies with
  `Id: 1966832731`). This makes you the admin. For several admins, separate with
  commas: `ADMIN_IDS=111,222`.
- **JWT_SECRET** — any long random text (just mash the keyboard, 40+ characters).

Save the file (**Cmd + S**) and close TextEdit.

✅ Your settings are ready. (This file stays only on your Mac — it's private.)

---

## Step 5 — Start the bot

In Terminal, run:
```bash
docker compose up --build
```
The first time, this takes a few minutes (it downloads and builds everything).
You'll see lots of text scrolling — that's normal.

✅ When it stops scrolling and shows lines like `gateway ... Application startup
complete`, it's running. Leave this window open — closing it stops the bot.

**Check it's healthy:** open a new browser tab to
**http://localhost:8000/health** — you should see `{"status":"ok",...}`.

---

## Step 6 — Try it in Telegram 🎉

Open Telegram and message **your bot**:

1. `/start` → it welcomes you.
2. `/grant 1966832731 monthly` → (use **your** id) it gives you a key for free,
   as the admin. The bot sends you your **API key**.
3. `/status` → shows your plan and expiry.
4. `/plans` → shows the plans with Buy buttons.

✅ If the bot replies, **everything works!**

---

## Stopping & starting again

- **Stop:** click the Terminal window and press **Ctrl + C** (then optionally run
  `docker compose down`).
- **Start again later:** open Terminal in the folder (Step 3) and run
  `docker compose up` (no `--build` needed after the first time).

---

## If something looks stuck 🛟

- **"Cannot connect to the Docker daemon"** → Docker Desktop isn't running. Open
  it and wait for the steady whale 🐳, then try Step 5 again.
- **"port is already allocated"** → something else uses port 8000 or 5432. Close
  other apps, or restart your Mac, and try again.
- **The bot doesn't reply** → double-check `BOT_TOKEN` in `.env` is correct and
  you messaged the right bot. After editing `.env`, stop (Ctrl+C) and run
  `docker compose up` again.

---

## Want more?

- Try the product API from the command line:
  `python3 scripts/client_example.py --api-key YOUR_KEY --fingerprint my-mac`
- Full details & concepts: [`docs/vault/Runbook.md`](docs/vault/Runbook.md) and
  [`README.md`](README.md).

> ⚠️ **Important:** after testing, regenerate your bot token in **@BotFather**
> (`/token`) if you ever shared it anywhere, and update `BOT_TOKEN` in `.env`.
