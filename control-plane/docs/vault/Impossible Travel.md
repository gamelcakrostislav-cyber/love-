---
tags: [concept, anti-abuse]
---
# Impossible Travel

_Source: `app/services/risk.py`, `app/services/geoip.py`_

A risk signal for [[Session Token|session]] issuance. Each session's IP + time is
recorded in a Redis trail; if **consecutive sessions for the same key imply a
ground speed above `IMPOSSIBLE_TRAVEL_MAX_KMH`** (default 1000 km/h — faster than
a plane), that's physically impossible for one human, so the [[API Key]] is
flagged ([[Anti-Abuse]]).

- Geo resolution via a **pluggable stub** (`geoip.py`, swappable for MaxMind/API)
  with a test-injection hook; private/unknown IPs are skipped.
- Distance via haversine; `speed = distance / Δt`.
- Detection **flags, not bans** — records an `abuse_event` with detail like
  `"203 km in 2 min = 6090 km/h"` and bumps `risk_score`.

Part of step 6 of the [[Licensing Model|enforcement pipeline]].
