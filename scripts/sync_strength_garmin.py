#!/usr/bin/env python3
"""
Create the strength sessions (Strength A / B + ISO) from roam/20250327164425-course.org
as native Garmin Connect "Strength" workouts: per-exercise animations, auto rep
counting and rest timers on the watch. intervals.icu can NOT push strength workouts
to Garmin (run/ride pipeline only), so this talks to Garmin Connect directly through
the unofficial API (garminconnect library — same auth flow as the mobile app).

SETUP
  python3 -m pip install garminconnect
  python3 sync_strength_garmin.py login    # once: email + password (+ MFA code if
                                           # asked). Saves a token in ~/.garminconnect;
                                           # the password is NEVER written to disk.

USAGE
  python3 sync_strength_garmin.py dry        # preview the 3 sessions (no network)
  python3 sync_strength_garmin.py create     # create the missing sessions (idempotent)
  python3 sync_strength_garmin.py schedule   # put A on Mon+Sat + B on Thu on the
                                             #   Garmin calendar (idempotent) -> auto-push
  python3 sync_strength_garmin.py unschedule # remove those calendar entries (undo)
  python3 sync_strength_garmin.py list       # list the account's workouts
  python3 sync_strength_garmin.py delete     # delete OUR 3 sessions (by name)

NOTES
- Workouts appear on the watch (Training > Workouts) at the next sync — no need
  to schedule them on the calendar: launch A on Mon + Sat (post-long-run), B on Thu.
- TEMPO (3-0-3…) can't be encoded on Garmin → it lives in each step's
  description; count in your head.
- "Per leg" reps: Garmin counts the total → do L then R before resting.
- Exercise keys verified against the official catalog
  (connect.garmin.com/web-data/exercises/Exercises.json).
- Optional: GARMINTOKENS=/path to relocate the token; GARMIN_EMAIL /
  GARMIN_PASSWORD for a non-interactive login (used by the org block).
"""
import os
import sys
import time
import datetime as dt

TOKENSTORE = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))
SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training"}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}

# Calendar auto-scheduling (mode `schedule`): which session on which weekday (0=Mon..6=Sun).
# A on Mondays + Saturdays (post-long-run plantar dose, decided Jul 9 2026 -- Rathleff
# frequency for the chronic plantar fasciopathy), B on Thursdays. Strength always AFTER
# a run, never the day before the long run.
# ISO is deliberately NOT scheduled (it's an as-needed flare-up option).
SCHED_WEEKDAY = {0: "Strength A - calf/plantar (HSR, slow tempo)",
                 3: "Strength B - quad/knee/hip (slow tempo)",
                 5: "Strength A - calf/plantar (HSR, slow tempo)"}
# Saturdays where the post-long-run A must NOT land: race day, day-before-race,
# or the recovery-week Saturday. (Mon/Thu are never in this set.)
SKIP_DATES = {dt.date(2026, 8, 8),    # day before UTFS 10 km (Sun Aug 9)
              dt.date(2026, 9, 19),   # Beluga 18 km race day
              dt.date(2026, 10, 3),   # day before the half (Sun Oct 4)
              dt.date(2026, 10, 24),  # 30 km goal day
              dt.date(2026, 10, 31)}  # recovery-week Saturday
PLAN_START = dt.date(2026, 6, 29)   # week 1 Monday
PLAN_END = dt.date(2026, 10, 31)    # end of week 18 (last strength Thu Oct 29)
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ex_step(order, category, name, desc, reps=None, secs=None):
    """One exercise step: by reps (auto count) or by duration (isometric)."""
    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
        "description": desc,
        "targetType": NO_TARGET,
        "category": category,
        "exerciseName": name,
    }
    if reps is not None:
        step["endCondition"] = {"conditionTypeId": 10, "conditionTypeKey": "reps"}
        step["endConditionValue"] = float(reps)
    else:
        step["endCondition"] = {"conditionTypeId": 2, "conditionTypeKey": "time"}
        step["endConditionValue"] = float(secs)
    return step


def rest_step(order, secs):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 5, "stepTypeKey": "rest"},
        "description": f"Rest {secs} s",
        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        "endConditionValue": float(secs),
        "targetType": NO_TARGET,
    }


# (sets, category, exercise, reps, iso_seconds, description, rest_s)
# Plan source: "Strength program (sessions A / B)" section of course.org.
SEANCES = [
    ("Strength A - calf/plantar (HSR, slow tempo)", "Monday, AFTER the easy run. RPE 7-8, add load once a set feels easy.", [
        (3, "CALF_RAISE", "SINGLE_LEG_STANDING_CALF_RAISE", 8, None,
         "Knee STRAIGHT, forefoot on a step, TOES on a rolled towel (Rathleff). "
         "Tempo 3s up / 2s hold / 3s down. 8 reps PER LEG (L then R).", 75),
        (3, "CALF_RAISE", "SINGLE_LEG_BENT_KNEE_CALF_RAISE", 10, None,
         "Knee BENT ~30 deg (soleus). Tempo 3-1-3. 10 reps PER LEG.", 60),
        (2, "HIP_RAISE", "SINGLE_LEG_HIP_RAISE", 10, None,
         "Single-leg glute bridge (glutes + hamstrings). Tempo 2-1-2. 10 reps PER LEG.", 45),
    ]),
    ("Strength B - quad/knee/hip (slow tempo)", "Thursday, AFTER the easy run. Telemark carryover. RPE 7-8.", [
        (3, "LUNGE", "DUMBBELL_BULGARIAN_SPLIT_SQUAT", 8, None,
         "Bulgarian split squat (rear foot elevated). Bodyweight wks 1-2, then add load. "
         "Tempo 3s down / 0 / 1s up. 8 reps PER LEG.", 75),
        (2, "SQUAT", "ELEVATED_SINGLE_LEG_SQUAT", 8, None,
         "= eccentric step-down from a step: 3s down, assisted back up. "
         "Sensitive patellar tendon -> replace with a 30-45s wall-sit. 8 reps PER LEG.", 60),
        (2, "PLANK", "SIDE_PLANK_WITH_LEG_LIFT", 12, None,
         "Side plank + top-leg raise (or lateral band walk). "
         "12 reps PER SIDE.", 45),
    ]),
    ("Strength ISO - flare-up days (pain relief)", "Acute flare-up days: ONLY the isometrics (plan, Strength progression section).", [
        (5, "CALF_RAISE", "STANDING_CALF_RAISE", None, 45,
         "ISOMETRIC hold at mid-height, 45 s, heavy if tolerated (tendon pain relief).", 60),
        (3, "SQUAT", "BODY_WEIGHT_WALL_SQUAT", None, 45,
         "Wall-sit (quad/patellar isometric), thighs ~parallel to the floor, 45 s.", 60),
    ]),
]


def build_payload(name, desc, blocks):
    steps, order = [], 1
    for nsets, cat, exname, reps, secs, stepdesc, rest_s in blocks:
        steps.append({
            "type": "RepeatGroupDTO",
            "stepOrder": order,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
            "numberOfIterations": nsets,
            "smartRepeat": False,
            "workoutSteps": [
                ex_step(1, cat, exname, stepdesc, reps=reps, secs=secs),
                rest_step(2, rest_s),
            ],
        })
        order += 1
    return {
        "workoutName": name,
        "description": desc,
        "sportType": SPORT,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": SPORT, "workoutSteps": steps}
        ],
    }


def payloads():
    return [build_payload(n, d, b) for n, d, b in SEANCES]


def summarize(p):
    lines = [f"{p['workoutName']}  ({p['description']})"]
    for g in p["workoutSegments"][0]["workoutSteps"]:
        work = g["workoutSteps"][0]
        rest = g["workoutSteps"][1]
        if work["endCondition"]["conditionTypeKey"] == "reps":
            dose = f"{g['numberOfIterations']} x {int(work['endConditionValue'])} reps"
        else:
            dose = f"{g['numberOfIterations']} x {int(work['endConditionValue'])} s"
        lines.append(f"  - {dose:<12} {work['category']}/{work['exerciseName']}"
                     f"  (rest {int(rest['endConditionValue'])} s)")
        lines.append(f"      {work['description']}")
    return "\n".join(lines)


def mfa_prompt():
    try:
        return input("Garmin MFA code: ").strip()
    except EOFError:
        sys.exit("MFA required but no interactive terminal -> run "
                 "`python3 sync_strength_garmin.py login` in a terminal.")


def get_client(with_credentials=False):
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("Missing module -> python3 -m pip install garminconnect")
    if with_credentials:
        email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
        password = os.environ.get("GARMIN_PASSWORD")
        if not password:
            import getpass
            password = getpass.getpass("Garmin password: ")
        g = Garmin(email=email, password=password, prompt_mfa=mfa_prompt)
        g.login(TOKENSTORE)
        return g
    try:
        g = Garmin()
        g.login(TOKENSTORE)
        return g
    except Exception as e:
        sys.exit(f"No valid Garmin session ({type(e).__name__}: {e})\n"
                 f"-> first run: python3 sync_strength_garmin.py login")


def _scheduled_index(g, start, end):
    """(date_iso, workoutId) -> calendar item id, over the months spanned by [start, end]."""
    idx, y, m = {}, start.year, start.month
    while (y, m) <= (end.year, end.month):
        for it in (g.get_scheduled_workouts(y, m) or {}).get("calendarItems", []):
            if it.get("workoutId") and it.get("date"):
                idx[(it["date"], it["workoutId"])] = it.get("id")
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return idx


def do_schedule(g, name_to_id):
    """Put Strength A on every Monday + Saturday (minus SKIP_DATES) and B on every
    Thursday of the plan, from today on.
    Idempotent: skips days already carrying that workout. Gentle pacing to dodge 429s."""
    start = max(dt.date.today(), PLAN_START)
    have = _scheduled_index(g, start, PLAN_END)
    added = skipped = 0
    d = start
    while d <= PLAN_END:
        wid = name_to_id.get(SCHED_WEEKDAY.get(d.weekday()))
        if wid and d not in SKIP_DATES:
            if (d.isoformat(), wid) in have:
                skipped += 1
            else:
                g.schedule_workout(wid, d.isoformat())
                print(f"scheduled {d.isoformat()} {DOW[d.weekday()]}  {SCHED_WEEKDAY[d.weekday()]}")
                added += 1
                time.sleep(0.4)
        d += dt.timedelta(days=1)
    print(f"{added} strength session(s) added to the Garmin calendar ({skipped} already there). "
          f"Sync the watch -> they push automatically on the day (A Mon+Sat, B Thu).")


def do_unschedule(g, name_to_id):
    """Remove OUR scheduled A/B strength entries from the calendar (undo `schedule`)."""
    ours = {name_to_id.get(n) for n in SCHED_WEEKDAY.values()} - {None}
    removed = 0
    for (date, wid), cal_id in sorted(_scheduled_index(g, PLAN_START, PLAN_END).items()):
        if wid in ours and cal_id:
            g.unschedule_workout(cal_id)
            print(f"unscheduled {date}")
            removed += 1
            time.sleep(0.3)
    print(f"{removed} strength session(s) removed from the calendar.")


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "dry").lower()
    ours = payloads()

    if mode == "dry":
        for p in ours:
            print(summarize(p))
            print()
        print(f"{len(ours)} sessions ready. Nothing sent (dry mode) -> "
              f"`create` to create them in Garmin Connect.")
        return

    if mode == "login":
        g = get_client(with_credentials=True)
        name = getattr(g, "full_name", None) or "?"
        print(f"Logged in: {name}. Token saved in {TOKENSTORE} -> "
              f"create/list/delete now work without a password.")
        return

    g = get_client()
    existing = {w.get("workoutName"): w.get("workoutId") for w in g.get_workouts(0, 200)}

    if mode == "list":
        for w in g.get_workouts(0, 200):
            sport = (w.get("sportType") or {}).get("sportTypeKey", "?")
            print(f"{w.get('workoutId')}  [{sport}]  {w.get('workoutName')}")
        return

    if mode == "schedule":
        do_schedule(g, existing)
        return

    if mode == "unschedule":
        do_unschedule(g, existing)
        return

    if mode == "create":
        for p in ours:
            name = p["workoutName"]
            if name in existing:
                print(f"already exists (id {existing[name]}): {name} -- skip "
                      f"(`delete` first to recreate)")
                continue
            res = g.upload_workout(p)
            wid = res.get("workoutId", "?")
            print(f"created: {name} -> https://connect.garmin.com/modern/workout/{wid}")
        print("Done. Sync the watch (Garmin Connect mobile or wifi) -> "
              "Training > Workouts on the watch.")
        return

    if mode == "delete":
        found = False
        for p in ours:
            wid = existing.get(p["workoutName"])
            if wid:
                g.delete_workout(wid)
                print(f"deleted: {p['workoutName']} (id {wid})")
                found = True
        if not found:
            print("none of our sessions on the account -- nothing to delete")
        return

    sys.exit(f"unknown mode: {mode} "
             f"(expected: dry/login/create/list/delete/schedule/unschedule)")


if __name__ == "__main__":
    main()
