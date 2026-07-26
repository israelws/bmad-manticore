---
name: mc-retro
description: Turn post-publish notes into pipeline improvements. Use after a video ships, or when the user says "retro", "here is my feedback", or "wrap up this project".
---

# mc-retro

The compounding mechanism: feedback edits FILES, not just memory. Every note lands in a taste file that the next run obeys, which is why a note left in the conversation is lost work. The consumer of your edits is a later stage reading those files cold, with none of this session in the room.

Two lanes. Retro routes the creator's notes into the files that would have prevented them. Wrap does post-publish cleanup and asset promotion. Retro runs first and offers wrap after; the creator can also ask for wrap alone on an already-retroed project.

## On Activation

1. Studio config: `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`. Empty means mc-setup has not run: stop and route the creator there. Resolve `paths` values against `{project-root}`.
2. This skill's surface: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root}`. Run `{workflow.activation_steps_prepend}` before the rest of activation and `{workflow.activation_steps_append}` after it; hold `{workflow.persistent_facts}` as standing context.
3. Establish the target. With a project, read `project.json` (stage `retro`) and take the format from it. On an ad-hoc run with no `project.json`, ask which format profile in `{formats-path}` the notes concern, or which brand file directly (`voice-bible.md`, `blacklist.md`, `production-bible.md`), and route to that. Ad-hoc runs skip only the `project.json` bookkeeping, so ad-hoc feedback still compounds.

## Collecting the notes

Read the files that may receive edits before asking for anything: `{brand-path}/voice-bible.md`, `{brand-path}/blacklist.md`, `{brand-path}/production-bible.md`, and the target format profile. Then take one round of notes: what felt wrong, what they re-edited in their editor, what they rewrote in the script, what looked off on screen, packaging performance (Test & Compare results if run). One round per session; do not fish for endless feedback.

## Routing

Every note goes to the file that would have prevented it.

- Voice or wording miss: a rule in `{brand-path}/voice-bible.md` carrying the verbatim example, and/or a new pattern in `{brand-path}/blacklist.md`.
- Visual style miss (graphics density, overlay aesthetic, image-type choice, CTA placement): `{brand-path}/production-bible.md`, global section or the matching per-format override section.
- Structural or retention miss: the Learnings section of `{formats-path}/<format>.md`.
- A stage doing the wrong thing: that skill's durable per-skill surface first, meaning a `workflow.persistent_facts` entry or the matching `workflow` key (e.g. one of the `*_flags`) in `{project-root}/_bmad/custom/<skill>.toml`. That is the team-override layer resolve_customization.py loads on every activation and module updates never touch (the same file where mc-setup records mc-cut's `cutplan_flags`); edit it surgically, preserving existing keys. Editing that skill's installed SKILL.md is the last resort, only when the note fits nowhere else, because module updates may overwrite it. If the harness blocks access to another skill's folder, record the note in the format profile's Learnings instead.
- A tool being driven wrong: the `notes` field of that tool's `[[tools]]` entry in the studio config (`[modules.manticore]` in `{project-root}/_bmad/custom/config.toml`).
- A mechanical failure: an issue note in the relevant engine README or script docstring.
- A pipeline gap, meaning a stage could not do its job because the module itself is missing a feature, has a wrong contract, or has a broken mechanic: an entry in the improvements log below, in addition to any local fix above.

Entries are ISO-dated, newest first, and one-way: the blacklist, Learnings, the production bible, and the improvements log only accumulate, so a change of taste is a new dated entry that supersedes by date rather than a deletion. Deletions are the creator's call.

Make the edits small and surgical, one note one edit at the point of failure, and show the creator the diff summary. A repeated override of the cut stage's judgment in the editor is itself one note: mine the pattern ("always keep pre-demo breaths") into the format profile's Learnings.

Never weaken a gate or remove a hard rule in response to convenience feedback; flag those for the creator explicitly.

## Improvements log

The structured upstream feedback channel, so module maintainers get comparable reports from every studio. mc-retro, and any stage that hits a pipeline gap mid-run, appends to `improvements-log.md` in the studio root, the parent folder of `{brand-path}` (with default paths that is `manticore/improvements-log.md`). Create it with a `# Improvements log` heading if missing. One line per entry, append-only, newest first under the heading:

`- YYYY-MM-DD [stage/skill]: what happened; why it is a gap; suggested fix; severity: low|medium|high`

Entries describe module gaps, not creator taste. Taste goes to the brand and format files per the routing above.

## Wrap lane

Post-publish cleanup for a shipped project; requires a project folder.

Nothing is reclaimed until the creator confirms the final master exists at its published or archived location. That confirmation is a hard stop: no part of this lane runs on assumption.

- Reclaim reproducible render scratch: preview renders, intermediate proxies, render caches, anything regenerable from `edl.json` plus the sources. List every candidate with its size, subtract anything matching `{wrap.preserve}`, and delete only after the creator approves the list. Never candidates: source footage, transcripts, `edl.json`, the cutplan, overlays, `project.json`, and the master itself.
- Enforce one blessed asset per slot: for each asset slot (thumbnail, title card, any overlay with multiple candidates), keep only the shipped version; rejected candidates move to the reclaim list or an archive folder, the creator's choice.
- Promote evergreen assets: anything useful beyond this video (reusable overlays, diagrams, series templates) moves to the series `common/` folder beside its project folders under `{projects-path}`; anything brand-wide moves to `{brand-path}`. Write or update a `README.md` in each destination listing each promoted asset, the project it came from, and the ISO date.

Durable rules discovered during wrap route like any other note.

## Closing out

In `project.json` (skip on ad-hoc runs), append `retro` to `stages_done` and set `stage` to `done`, append the retro notes and whether wrap ran to its `notes` field, and report.
