---
name: update-blog
description: Regenerate the training pages and deploy the blog (stacktrace.run) — after annotation edits, program changes, or template changes, without a new data pull. Use when the blog needs rebuilding/publishing.
---

# Update + deploy the blog

Repo: `~/blog` (Hugo + PaperMod + ox-hugo → nginx on Joel's VPS,
https://stacktrace.run).
Full conventions: `~/blog/CLAUDE.md` and `~/blog/README.md`.

## Steps

1. **Regenerate** the data-driven pages:
   `cd ~/blog && python3 scripts/generate_training_pages.py`
   (log, health draft, calendar, weeks.json, per-run posts, prompt-template
   page — all from `~/org` data; per-run notes live in that script's
   `ANNOTATIONS` dict).
2. **Export org content** if `content-org/blog.org` changed:
   ```sh
   emacsclient --eval '(let ((enable-local-variables :safe))
     (with-current-buffer (find-file-noselect "~/blog/content-org/blog.org")
       (revert-buffer :ignore-auto :noconfirm)
       (prog1 (org-hugo-export-wim-to-md :all-subtrees) (kill-buffer))))'
   ```
3. **Build + confirm**: any NEW page must exist under `public/` after the
   build (future-dated pages are silently skipped; use today's real date).
4. **Deploy**: `scripts/deploy.sh` — Hugo build + rsync to the VPS webroot
   (`stacktrace.ca:/srv/http/stacktrace.run/`, joel-owned, no sudo).
   Unmetered — deploy as often as needed.
5. **Verify live**: curl the changed pages on https://stacktrace.run.
6. **Commit + push for history** (does not deploy). Commits are SSH-signed
   via 1Password: "failed to write commit object" means it's locked → ask
   the user to unlock, never disable signing.

## Conventions

- `DONE` subtree = published, `TODO` = draft. The health page stays draft
  unless the user explicitly says to publish.
- Hugo shortcodes in org must sit in `#+begin_export hugo … #+end_export`.
- Program changes get a dated changelog entry on "The program — current";
  never touch "The program — as designed" (frozen snapshot).
- English, the user's first-person voice, real numbers only (from
  run-log/wellness-log — never invented).
