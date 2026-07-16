---
name: sync-runs
description: Pull latest runs + wellness from intervals.icu, analyze them against the training plan, and update/deploy the blog. Use when the user says they ran, asks to sync/pull activities, or wants a training catch-up.
---

# Sync runs from intervals.icu (+ analyze + publish)

## 1. Pull

```sh
cd ~/org && python3 sync_plan_intervals.py pull
```

- Pulls new runs into `run-log.org`, daily wellness into `wellness-log.org`,
  refreshes `plan-30k-agenda.org` (DONE marks), and re-loads strength
  activities from RPE so they count in CTL/ACWR.
- **401 error** → the intervals.icu API key lives in `~/.authinfo.gpg`, read
  via emacsclient auth-source, and GPG is locked: ask the user to open
  `~/.authinfo.gpg` in Emacs (pinentry caches the passphrase), then retry.
  Never print the key.

## 2. Analyze

Read the new entries at the end of `run-log.org` and today's row in
`wellness-log.org`, and the matching scheduled session in
`plan-30k-agenda.org`. Report to the user:

- Planned session vs executed: duration vs cap, distance, pace.
- Zone discipline: % Z2 (target: everything Z2, easy runs genuinely easy —
  the plan's #1 recurring fault is easy-too-hot; >=70 % Z2 is good,
  >=30 % above Z2 is hot).
- HR avg/max vs the Z2 band (130-145, LTHR 173).
- Wellness context: RHR 7d (green <=42), HRV 7d (green trending ~60+),
  sleep. These + the foot morning-score trend gate progressions.
- Flag anything off-plan (over cap, unscheduled day, missed session) —
  neutrally; the plan absorbs, never "makes up".

## 3. Publish (standing rule — do without being asked)

Follow `~/org/CLAUDE.md` → "Running blog": regenerate
(`cd ~/blog && python3 scripts/generate_training_pages.py`), add an
`ANNOTATIONS` entry in that script for each notable run (long/race/off-plan
always; routine runs only if something happened), rerun the generator,
deploy with `~/blog/scripts/deploy.sh` (Hugo build + rsync to the VPS,
unmetered, ~2 s), verify the live pages, then commit + push for history
(pushing does NOT deploy).
