---
name: garmin-strength
description: Create, schedule, or manage the strength sessions (A/B/ISO) as native Garmin watch workouts. Use for anything touching Garmin Connect strength workouts or their calendar scheduling.
---

# Garmin strength workouts

Driver: `~/org/sync_strength_garmin.py <mode>`.

## Modes

- `dry` — local preview.
- `login` — first time / expired token only. Interactive (email + password,
  possibly MFA) → have the USER run it in a terminal
  (`python3 ~/org/sync_strength_garmin.py login`); the password is never
  written to disk, the OAuth token lands in `~/.garminconnect`. 429s on the
  SSO transports are benign if the final "Logged in" line appears (IP
  rate-limiting).
- `create` — create Strength A (calf/plantar HSR), B (quads/glutes) and ISO
  (flare-day isometrics) as native Garmin "Strength" workouts with
  animations, rep counting and rest timers. Idempotent.
- `schedule` — put A on Mondays + Saturdays (post-long-run plantar dose;
  `SKIP_DATES` excludes race days, day-before-race, recovery-week
  Saturdays) and B on Thursdays. Idempotent. **Re-run after any plan
  shift.**
- `unschedule` / `list` / `delete`.

## Notes

- Tempo can't be encoded in Garmin steps — it lives in each step's
  description. "Per leg" reps: Garmin counts totals, so do L then R before
  resting.
- Recorded strength syncs to intervals.icu with ~0 HR load; the pull's
  RPE→load fix (see sync-runs) is what makes it count in CTL/ACWR.
- The exercise content (sets/tempo/videos) is documented in
  `roam/*course.org` → "Strength program" and published at
  /running/strength/ on the blog.
