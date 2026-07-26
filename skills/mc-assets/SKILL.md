---
name: mc-assets
description: Farm the stills and b-roll the beats need. Use at the assets stage, or when the user says "farm the assets", "find the images", or "get the b-roll".
---

# mc-assets

Farm every still and clip the approved beat table calls for. The outcome is `assets/` holding exactly one blessed file per beat-row `asset` slot, plus `assets/manifest.json` recording where each one came from. mc-graphics composes overlays against these files and the final render puts them on screen at full size, so that is the bar: the right thing depicted, sourced as high up the Production Bible's hierarchy as the shot allows, and clean at zoom. A generation that misrepresents something real is worse than no asset at all.

## Resolution rules

- Bare paths resolve against `{video-path}`, the current video project at `{projects-path}/<slug>/`. Every bare `assets/` below is that project's folder, never a skill folder.
- `{skill-root}` → this skill's installed directory; files in it always carry it (`{skill-root}/references/generative-editing-rules.md`).
- `{project-root}` → the project working directory.
- `{skill-name}` → the skill directory's basename.

## On Activation

1. Load the studio config: `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`. Empty means mc-setup has not run: stop and route the creator there. Resolve `paths` values against `{project-root}`.
2. Read `project.json` (stage `assets`), `beats/beats.md`, the format profile, and `{brand-path}/production-bible.md`, whose image-type policy and sourcing hierarchy govern every choice here. The rows to farm are the ones whose `asset` column names an id; a 0.x table with no `asset` column has nothing to farm. If the profile says `generated_broll: banned`, stop and report, because something upstream is wrong.

Before any generative farm or revision, load `{skill-root}/references/generative-editing-rules.md`. Its rules on chaining, compositing, self-inspection, people, and prompting bind every lane and every provider.

## Sourcing

Real verified imagery first: the creator's own libraries at the locations the bible names, screen recordings, verified photos. Generative only for what does not exist. A hand-built text card last.

Generated footage never depicts UI or text that has to be accurate; real UI comes from screen recordings, and claim-bearing text belongs to mc-graphics' SVG/diagrammatic lane rather than to farming. Any asset with the creator or another person in it starts from an approved original photo in `{brand-path}/headshots/` passed as `--ref`.

## Lanes

`[assets]` names the lane per kind: `image-provider`, `video-provider`, `escalation-provider`. Each value is either the `name` of a registered `[[tools]]` CLI (the working default in 1.0) or a metered API lane (`xai-api`, `veo-api`, both unimplemented until 1.0.x). If the lane an asset needs is empty or names nothing registered, STOP and ask the creator which registered tool to use, routing to mc-setup's tool registration if none exists. Never fall back to a metered lane the creator did not explicitly choose.

## Farming

Farm by tool NAME through the script, so no session has to remember how a tool is driven. Save the resolved config as JSON once:

`uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore > <resolved assets/work/.farm-config.json>`

Then, per asset, write the prompt per the generative editing rules and run:

`uv run {skill-root}/scripts/farm_asset.py --kind image|video --prompt "..." --provider <the [assets] lane value> --config <the saved config JSON> --out-dir <resolved assets/work/> [--seconds 8] [--ref <real photography or the original source only>]`

The script prints the tool's `notes` first, which are the persistent memory for driving that tool, and appends a provenance row per new file to `assets/work/manifest.json`. Escalate to `escalation-provider` only for hero shots where realism must not wobble.

Video generation and large batches run in the background with proactive progress; never leave the creator staring at a silent stage. When project.json carries an event deadline (set at mc-new), order the remaining assets by their hard external gates and cap iteration loops: a shipped asset at the deadline beats a perfect asset after it.

## Blessing

Candidates, drafts, and retries stay in `assets/work/`. When the creator picks, copy exactly one blessed file per beat-row slot into `assets/`, named by its asset id, and append its work-manifest row to `assets/manifest.json` (file, kind, prompt, provider, model, cost, date). Report total spend for the lanes that report cost; registered CLI tools draw on the creator's own subscription and report none.

Then update project.json: append `assets` to `stages_done` and set `stage` to the next stage in its `stages` list.

## Checklist

- Exactly one blessed file in `assets/` per beat-row `asset` slot; every alternate and retry stayed in `assets/work/`.
- `assets/manifest.json` carries a row per blessed file, with spend summed for the lanes that report it.
- Nothing in `assets/` shows readable UI or misrepresents anything real, and every short quoted string is character-exact.
