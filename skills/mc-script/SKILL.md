---
name: mc-script
description: Weave the script from outline and braindump. Use at the script stage after gate 1, or when the user says "write the script" or "draft the script".
---

# mc-script

The anti-LLM-slop stage. The script is woven, not written: everything worth saying is already in `braindump.md`, and your craft is the weave. The outcome is `script.md`, performed to camera by the creator who dumped it. Read every line aloud in your head at their pace; anything you stumble on, they will too.

## Resolution rules

- Bare paths and `{skill-root}` (e.g. `scripts/lint_script.py`) resolve from this skill's installed directory.
- `{project-root}` is the project working directory; the studio config's `paths` values resolve against it.

## On Activation

1. Resolve the studio config: `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`. Empty means mc-setup has not run: stop and route the creator there.
2. Resolve this skill's surface: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root}`. Run `{workflow.activation_steps_prepend}` now, `{workflow.activation_steps_append}` after activation, and hold `{workflow.persistent_facts}` as standing context.
3. Read `project.json` (confirm gate 1 passed: `approvals.outline` is a date, stage is `script`), `outline.md`, `braindump.md`, `{brand-path}/voice-bible.md`, 1 to 2 files from `{brand-path}/exemplars/`, and the format profile.

## The weave

Work beat by beat under the quote-or-cut contract:

- Lift the creator's braindump phrasing directly, smoothing only for spoken flow.
- Every sentence either traces to a braindump passage or carries an inline `[INVENTED]` flag. Flags are for connective tissue only; a content claim that needs inventing is a gap in the braindump, so ask the creator. If more than roughly a quarter of the sentences would need a flag, stop and send the project back to mc-braindump: the raw material is not there yet.
- Write the hook LAST, from the approved candidate, once the body proves what the hook can promise.
- No stage directions, no camera notes, no "(pause)" theater unless the creator asked for them.

## The CTA

Weave the configured CTA line(s) from `[cta]` in the studio config, following the outline's CTA plan line and craft rule 15. CTA copy is the one sanctioned exception to quote-or-cut: it comes from the configured items (kind, label, url), not the braindump, and needs no `[INVENTED]` flag. If `[cta]` is empty, weave no ask rather than invent one.

## Lines already on camera

If project.json `sources` has an `interview` recording, transcribe it if not yet done (mc-cut's transcribe.py) and mark every script line whose phrasing was already spoken well on camera with an inline `[TAKE <source-id> <start>s-<end>s]` from the word timestamps. Those lines may not need re-recording, only reorganizing at the cut stage.

## QA before presenting

- `uv run {skill-root}/scripts/lint_script.py {projects-path}/<slug>/script.md --blacklist {brand-path}/blacklist.md`. Exit 1 lists violations; fix every one.
- Run the craft checklist at `{workflow.craft_checklist}`, plus the manual QA list at the bottom of the creator's blacklist.
- Runtime from the real word count at the creator's measured wpm (`[owner] wpm`), stated and flagged if it misses the format's target length.

## Handoff

Write `script.md` with the `[INVENTED]` flags still visible, update project.json (append `script` to `stages_done`, set `stage` to the next entry in its `stages` array), and present. The ball is then the creator's: record, drop takes in `raw/` at constant frame rate. Where `[TAKE ...]` markers exist, list the delta explicitly: which lines are already captured on the interview recording, which still need recording.
