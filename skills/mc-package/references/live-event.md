# Live-event mode (scheduled broadcasts)

For `livestream-pack` projects, packaging serves a scheduled broadcast rather than a finished
video. The deliverables are one title, one description, and one broadcast thumbnail, all aimed at
a stream that has not happened yet.

Load this instead of the VOD flow when the format is `livestream-pack` or `stages` contains
`stream-pack`. The Thumbnails, Description, and blessed-slot sections of `SKILL.md` still govern
how each asset is made; this file says what changes.

## What to produce

1. Apply the series template first when the show belongs to a series; recurring shows usually do.
   See `references/series-template.md`.
2. One title (locked anchors apply) and one description. This is the live lane, so live framing is
   correct here: chat asks, the schedule, membership mentions, alongside the CTA lines and
   `[owner]` `links` the Description section specifies.
3. ONE scheduled-broadcast thumbnail through the full Thumbnails flow: face plus a 2 to 4 word
   hook, programmatic draft, mandatory improvement pass, mandatory 120px verification.
4. No chapters and no captions; nothing is cut.

## The two-asset rule

The scheduled-broadcast thumbnail competes in browse and search exactly like a VOD thumbnail and
gets the full face-plus-hook treatment. It is NEVER a plain brand card.

The plain branded card with the countdown safe zone is a different asset with a different job: the
in-stream Starting Soon SCENE, produced by the stream-pack stage, not here. Never present one
asset for both jobs, and never let the scene card become the broadcast thumbnail.

## Finish

Write `packaging/titles.md`, `packaging/description.md`, and the thumbnail per the folder rules in
`SKILL.md`; update `artifacts` in `project.json`.

Touch `stage` and `stages_done` ONLY when `package` is the project's current stage AND appears in
its `stages` array. livestream-pack has no `package` stage (its stages are `new`, `stream-pack`,
`final`, `retro`), so leave both untouched and let mc-stream-pack advance the lane on the
creator's gate-4 approval.

Blessed slots apply once the creator approves the assets.
