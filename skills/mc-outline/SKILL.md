---
name: mc-outline
description: Draft hooks, the outline, and the packaging promise. Use at the outline stage, or when the user says "outline this", "write the outline", or "what is the hook".
---

# mc-outline

Gate 1. The outcome is `outline.md`: three hooks, one outline, and the packaging promise, in a form the creator can approve, edit, or kill before a line of script exists. It is a decision artifact, not a draft script. Everything in it traces to `braindump.md`, because the script stage may only use words already spoken there.

## Resolution rules

- Bare paths resolve against `{video-path}`, the current video project at `{projects-path}/<slug>/`.
- `{skill-root}` → this skill's installed directory; files in it always carry it (`{skill-root}/scripts/lint_script.py`).
- `{project-root}` → the project working directory.

## On Activation

1. Resolve the studio config: `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`. Empty means mc-setup has not run: stop and route the creator there. Its `paths` values resolve against `{project-root}`.
2. Resolve this skill's surface: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root}`. Run `{workflow.activation_steps_prepend}` now, `{workflow.activation_steps_append}` after activation, and hold `{workflow.persistent_facts}` as standing context.
3. Read `project.json` and confirm stage is `outline`, then `braindump.md`, the hook section of `{brand-path}/voice-bible.md` if it has been built, and the format profile.

## Three hooks

Three candidates, each built Target-Transformation-Stakes: who it is for, what they will be able to do, why it matters now. Use the creator's braindump phrasing wherever a phrase fits, and note which braindump line each hook leans on.

## One outline

One outline, not options: a tight beat list from hook to payoff. Every beat cites the braindump passage that fills it, and a beat with no material behind it is marked GAP with the question to ask the creator. Order for retention, with no throat-clearing beat at the top and open loops closed late.

Where the braindump names something the viewer should see, attach a visual-moment note to that beat, citing the passage and marked non-binding. mc-beats reads these as candidate compositions, not commitments.

## The packaging promise

The working title and thumbnail concept this video must pay off, plus a CTA plan line drawn from `[cta]` in the studio config: which configured CTA(s) this video will make and roughly where, sized to the configured appetite. If no CTAs are configured, the line says so.

If the video cannot pay off a clickable promise, say so now; that is a project problem, not a packaging problem.

## Before presenting

`uv run {skill-root}/scripts/lint_script.py {projects-path}/<slug>/outline.md --blacklist {brand-path}/blacklist.md`. Exit 1 lists blacklist violations; fix every one.

## Gate 1

Write it all to `outline.md`, set `approvals.outline = "pending"`, update `artifacts`, present to the creator, and STOP. Do not start the script. Do not describe what the script will say.

Only the creator's explicit say-so moves this gate. On approval, record the ISO date in `approvals.outline`, append `outline` to `stages_done`, and set `stage` to the next entry in project.json's `stages` array.
