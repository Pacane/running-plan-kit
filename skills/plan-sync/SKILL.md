---
name: plan-sync
description: Push the training plan to intervals.icu as structured workouts, regenerate the org agenda, or shift the plan (illness/life). Use when the plan's schedule must change on intervals.icu or the agenda needs regenerating.
---

# Sync the plan to intervals.icu

Driver: `~/org/sync_plan_intervals.py <mode>`.

## Modes

- `dry` — preview what would be created; always run before `create`.
- `create` — upsert the plan's workout events on intervals.icu (idempotent).
- `delete` — remove plan events.
- `org` — regenerate `plan-30k-agenda.org` only.
- `pull` / `wellness` / `fixstrength` — see the sync-runs skill.
- `whoami` / `latest` — auth + sanity checks.

## Env knobs

- `INTERVALS_EASY_MIN` (default 35) — easy-run duration; progression is
  sensation-gated, bump only when the user says so, then re-`create`
  upcoming easy events.
- `INTERVALS_SHIFT_WEEKS` + `INTERVALS_SHIFT_FROM` — shift the plan after
  illness/interruption, then `create`. Races keep their fixed dates.
  After any shift, also `unschedule` + `schedule` the Garmin strength
  sessions (see the garmin-strength skill).
- `INTERVALS_STRENGTH_RPE` (default 3) — strength load when no RPE logged.

## Rules

- Auth = `~/.authinfo.gpg` via emacsclient auth-source; 401 → have the user
  unlock GPG (open the file in Emacs), retry. Never print the key.
- `plan-30k-agenda.org`, `run-log.org`, `wellness-log.org` are GENERATED —
  never hand-edit.
- The master plan document (week table, principles, races) is
  `roam/*course.org` — hand-edited; plan changes there also require a dated
  changelog entry on the blog (see ~/org/CLAUDE.md → "Running blog").
