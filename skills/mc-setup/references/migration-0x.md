# Migrating a 0.x studio

Load this when `[modules.manticore]` exists but is missing any of the 1.0 tables
(`[render]`, `[style]`, `[cta]`, `[live]`, `[audio]`). That studio was configured
before 1.0.

Say so, then migrate rather than re-interviewing. Every existing value is already the
creator's answer and stays untouched; this pass only fills what 1.0 added.

## Backfill the config

- Write the missing tables in from `[defaults]` (render, style, cta, live, audio, plus
  the mechanical `cut`, `packaging` and `retro` sub-tables), editing the existing config
  surgically.
- If `[transcription] api-key-env` names a key the configured local provider never
  uses, blank it. Metered keys are set only when a metered provider is chosen.
- If the `[assets]` lanes still carry pre-1.0 defaults pointing at a metered API the
  creator never opted into or verified, flag it in the closing report and offer to
  repoint them at a registered CLI tool. Leaving them empty is also fine: mc-assets
  asks at farming time.

## Refresh the format profiles

For every profile in `{formats-path}` that also ships in `{skill-root}/assets/formats/`:

```
uv run {skill-root}/scripts/merge_profile_frontmatter.py \
    --shipped {skill-root}/assets/formats/<name>.md \
    --studio {formats-path}/<name>.md
```

It adds only the frontmatter keys new in 1.0 (`beat-types`, `density`, and any future
ones) that stages like mc-beats require. It never overwrites an existing key, the
creator's prose, or the Learnings. Then copy in any newly shipped profile that does not
exist in `{formats-path}` yet.

## Two things that moved

Interview footage recorded against the pre-1.0 marker cue ("question from claude") still
needs to segment. Offer the marker-cue question and record it as `cutplan_flags` in the
studio config's `[cut]` sub-table so cutplan keeps working on that footage.

A pre-1.0 series or thumbnail template at the brand root (for example
`thumbnail-template.md`) predates the `{brand-path}/templates/<series>.md` contract.
Offer to move it there, named for the series it describes, so mc-package finds it.

## Then run the delta

Interview only what 1.0 added: render consent, the video style interview, and audio
lanes.

Scaffold `{brand-path}/production-bible.md` seeded from what already exists (tokens.json,
shipped overlays, exemplars, format-profile learnings) plus the style answers, never from
a blank slate. This studio has history; a blank bible throws it away.

Offer without forcing: the HyperFrames graphics skills, headshot collection, the guided
voice bible, `.env.example`.

Finish with the normal write-and-report so the migrated config is verified and the
pending gaps are named.
