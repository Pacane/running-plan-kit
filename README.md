# running-plan-kit

The tooling behind [stacktrace.run](https://stacktrace.run) — an
injury-first, heart-rate-capped running program built and coached in
conversation with an AI, synced to intervals.icu and a Garmin watch, and
published as a blog. Background reading:
[how this works](https://stacktrace.run/posts/how-this-works/).

## What's here

```
prompt-template.org      The intake prompt. Fill in YOUR data, paste it into
                         an AI conversation (e.g. Claude), get your own plan.
                         This encodes the whole coaching methodology.
scripts/
  sync_plan_intervals.py   Plan -> intervals.icu structured workouts; pulls
                           completed runs, daily wellness (RHR/HRV/sleep) and
                           an org agenda back; strength load from RPE.
  sync_strength_garmin.py  Strength sessions as native Garmin watch workouts
                           (animations, rep counting), scheduled on the
                           calendar with race-weekend skips.
  generate_training_pages.py  Turns the org data into blog pages: run log
                           with per-run execution analysis, program calendar,
                           live week table, per-run posts. Hugo-flavored.
skills/                  Claude Code skills wrapping the workflows. Copy the
                         directories into your project's .claude/skills/ and
                         you get /sync-runs, /plan-sync, /garmin-strength,
                         /update-blog.
```

## Quick start

1. Read `prompt-template.org` → fill the `YOUR INTAKE` section with real
   data (a Strava/intervals.icu export beats guesses) → paste the whole
   file into an AI conversation. Answer its follow-ups honestly. You'll
   get a plan document plus the org files these scripts expect.
2. Skim each script's header — configuration is environment variables
   (`INTERVALS_API_KEY` or Emacs auth-source, `INTERVALS_EASY_MIN`,
   shift knobs, …). They assume your plan lives in `~/org`.
3. Optional: install the skills and let your AI drive the loop —
   "I ran today" → pull, analysis, blog update.

## Notes

- Built for one runner's setup, in conversation with an AI, and shared
  as-is: read before you run, adapt freely.
- No credentials live in this repo or these scripts — keys come from your
  environment; the Garmin OAuth token stays in your home directory.
- This produces a self-coached training plan, **not medical advice**. It
  is deliberately conservative and defers to a physio/physician for
  anything that looks like a real injury.
