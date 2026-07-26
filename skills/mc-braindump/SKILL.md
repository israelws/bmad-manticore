---
name: mc-braindump
description: Capture the creator's idea in their exact words. Use at the braindump stage, or when the user says "braindump", "let me talk this through", or "here is my idea".
---

# mc-braindump

The single most important input to the whole pipeline: the script stage may only use words that exist in this file (quote-or-cut). Capture generously.

## Resolution rules

- Bare paths resolve against `{video-path}`, the current video project at `{projects-path}/<slug>/`.
- `{skill-root}` → this skill's installed directory; files in it always carry it.
- `{project-root}` → the project working directory.

## On Activation

Load the studio config (`uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`; empty means mc-setup has not run: stop and route the creator there). Resolve `paths` values against `{project-root}`. Read `project.json` and `brief.md`. Confirm stage is `braindump`. Read the format profile at `{formats-path}/<format>.md` for the project's `format` and any taste files it names.

## Offer the camera first

Before the first question, always offer interview-recording mode: if the creator records this session at constant frame rate, their spoken answers double as potential takes. The convention is that they read each question to the lens as "Question from the interviewer: <the question>" before answering; that spoken marker cue is what lets mc-cut segment the recording mechanically. The cue is configurable (the setup interview; cutplan.py `--marker-cues`), and the older "question from claude" phrasing stays supported for studios that recorded with it.

## The interview

Whether or not the camera rolls, interview one question at a time, conversationally, until their phrasing starts repeating or they call it; there is no question count to hit. Goal: get the creator talking at length in their own phrasing. Capture each answer into `braindump.md` verbatim as it is given, never from conversation memory afterwards.

Cover, in whatever order the conversation goes: the core claim they actually believe, who it is for and what they get, the story they would tell a friend, the strongest objection and their answer to it, what everyone else gets wrong, the demo or proof they can show, and the payoff in one breath.

Ask the visual question verbatim: "what should the viewer see: demos, screens, drawings, motion, or moments you picture as a graphic?" mc-outline and mc-beats read that answer as candidate visual moments.

## The artifact

`braindump.md` is their answers lightly grouped under the question headings, their words untouched: fragments, slang and fillers all intact. Polishing destroys the corpus the script stage draws from.

If the session arrives as an external recording or transcript instead of a live conversation, save the raw transcript into the project's `raw/` first, then quote from it in `braindump.md`.

## Close out

If the session was recorded, have the creator drop the file into the project's `raw/` and register it in project.json `sources` with role `"interview"` (see the PIPELINE.md contract).

Update project.json: set `artifacts.braindump`, append `braindump` to `stages_done`, and set `stage` to the entry after `braindump` in this project's `stages` array. Stop.
