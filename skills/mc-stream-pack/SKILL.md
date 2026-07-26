---
name: mc-stream-pack
description: Build a branded livestream asset pack for OBS. Use on the livestream-pack format, or when the user says "stream assets", "OBS pack", or "scenes and stinger".
---

# mc-stream-pack

Brand tokens in, complete pack out. The `livestream-pack` format profile is the spec; this skill executes it. The outcome is a `graphics/` folder the creator loads into OBS and goes live from without you in the room, which is the bar: every asset verified, and HANDOFF.md saying where each one goes.

## Resolution rules

- Bare paths resolve against `{video-path}`, the current video project at `{projects-path}/<slug>/`.
- `{skill-root}` → this skill's installed directory; files in it always carry it (`{skill-root}/scripts/render_verify.py`).
- `{project-root}` → the project working directory.

## On Activation

1. Load the studio config: `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`. Empty means mc-setup has not run: stop and route the creator there. Resolve `paths` values against `{project-root}`.
2. Read `project.json` (stage `stream-pack`), the `livestream-pack` format profile, `{brand-path}/tokens.json`, and `{brand-path}/production-bible.md` when it exists: the styling contract beyond tokens, carrying the overlay and popup aesthetic for scenes and lower thirds, the per-series template sections, and the CTA section.

## Build the pack

The profile owns the scene list, reactivity, render formats, and durations. Scenes, lower thirds, and topic cards are self-contained local HTML in `graphics/scenes/`, styled entirely from tokens.json. The stinger is one HyperFrames comp in `{engines-path}/hyperframes/`, rendered to both formats the profile names.

Baked alpha deliverables headed for OBS browser or stinger use on any platform get their WebM VP9 alpha variant produced and verified in one step:

`uv run {skill-root}/scripts/render_verify.py graphics/<asset>.mov --transcode-webm graphics/<asset>.webm`

Checks default to yuva420p; add `--expect-res`/`--expect-fps`/`--expect-dur` from the profile.

When `[live] tool` is vmix or other, skip WebM: vMix rejects MP4 stingers and prefers PNG sequences, so deliver a sequence (`ffmpeg -i <master>.mov -pix_fmt rgba graphics/<asset>-png/%04d.png`) or the ProRes 4444 MOV. Wirecast takes the ProRes 4444 MOV directly.

Sound for the pack (the stinger whoosh, a Starting Soon music bed) routes through the mc-audio service skill; deliver the wavs alongside the scenes with their OBS wiring noted in HANDOFF.md.

## Verify

Run the profile's verification section. Scene screenshots land in `graphics/_verify/`. Stinger renders check via `uv run {skill-root}/scripts/render_verify.py`; the stinger and baked-asset WebM variants add `--pixfmt yuva420p`, or arrive already verified from the `--transcode-webm` call above.

## Hand off

Write `graphics/HANDOFF.md`: per asset, the OBS setup steps (browser source URLs and sizes, stinger transition settings). Then update project.json artifacts and advance stage per the profile's stages list (next after `stream-pack`, normally `final`), where the creator loads the pack in OBS and approves the look live.

## Checklist

- Every scene screenshot visually checked; no scene ships unseen.
- Countdown actually resets on scene re-activation (test via the obsstudio event, or document it as OBS-only behavior).
