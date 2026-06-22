---
tags: [concept, anti-abuse]
---
# Device Fingerprint

_Source: `app/services/devices.py`, `app/models/device.py`_

A stable, client-generated hardware/install id submitted at `/auth/session`. It
binds a [[Session Token]] to a machine and underpins anti-sharing.

- Each [[API Key]] allows `max_devices` registered fingerprints
  ([[Plans and Pricing]]). Unique per `(key_id, fingerprint)` in the [[Data Model]].
- A **new device beyond the limit** is parked in `cooldown` (24h,
  `DEVICE_REGISTER_COOLDOWN_HOURS`) and **auto-approves** afterward — so a key
  can't silently fan out to many machines at once.
- Managed by the user via [[Bot Commands|/devices]] (remove to free a slot).
- **Dedup**: the same fingerprint appearing under different accounts flags a
  multi-account cluster ([[Anti-Abuse]]).
- The token stores only `sha256(fingerprint)` (`dfp` claim), compared on each
  protected call.
