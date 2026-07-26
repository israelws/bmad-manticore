# Engine: Design Prompting

The authoring path when no registry block or brand template fits a beat: hand the beat to a capable design model as a structured design brief, iterate on the look in a review surface, then render the agreed look deterministically. Any design-capable model or surface works; Claude (Claude Design, Artifacts, and Claude Code) is the worked example throughout.

## The core rule

Design surfaces handle look and iteration, but pixels always come from deterministic frame-stepped rendering, never realtime screen recording. Realtime capture gives no alpha channel, a variable frame rate, and dropped frames. A design surface's live preview, a hosted review page, and any screen recording are review surfaces only, never deliverables.

- HyperFrames path: `npx hyperframes render` to ProRes 4444 (yuva444p10le) MOV for the editor lane, and a second render of the same comp to VP9 (yuva420p) WebM for the OBS/live lane. One comp, two renders, never two source comps.
- HTML path: a headless-Chrome harness seeks the animation to frame N, screenshots with a transparent background (`omitBackground: true` gives PNG alpha), then `ffmpeg -framerate {fps} -i frame_%05d.png -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le overlay.mov`.

## The determinism contract (required in every brief)

Designs authored in a chat or design surface default to wall-clock CSS animations that cannot be seeked. The contract that makes an HTML comp renderable:

- One single self-contained HTML file. No external requests of any kind (CDN scripts, fonts, images); inline or data-URI everything.
- All animation lives on one master timeline exposed as `window.seek(frame)`, which renders the exact state for that frame at the declared fps. Wall-clock CSS animations, `setInterval`, and `Date.now` are forbidden; use a seekable timeline (GSAP or WAAPI paused and seeked, or a pure function of frame).
- No unseeded randomness. Identical frame in, identical pixels out (render a frame twice and byte-compare to verify).
- Signal readiness: resolve `document.fonts.ready` before the first frame is captured.

HyperFrames beats satisfy the same contract natively: the comp is plain HTML/CSS plus a GSAP timeline created with `{ paused: true }` and registered on `window.__timelines`, which the renderer seeks per frame. Declare fps and duration in the comp's render config rather than inferring them.

## The design brief

The brief is a file (`graphics/briefs/<beat-id>.md`), reviewable and diffable. Omissions are where renders fail. Template:

```markdown
# Design brief: <beat-id> (one-line description)

## Beat (timing is law: do not change it)

- start {mm:ss.ms} / dur {s} / end {mm:ss.ms} on the edited timeline
- {N} frames at {fps} fps ({WxH})
- anchor word: "{word}" at {ts}; the graphic's key moment lands ON the anchor
- spoken phrase it rides on: "{verbatim phrase from the transcript}"
- composition intent: {one line from the beat row / storyboard}

## Exact text (verbatim: render these strings and nothing else)

1. "{string}"
No paraphrasing, no added copy, no lorem ipsum, no watermarks.

## Canvas and alpha

- Fully transparent background. No full-frame backdrops, vignettes, or scrims.
- Every pixel not part of the graphic has alpha 0 (verified over checkerboard).
- Safe zones: keep inside {title-safe %}; the speaker occupies {region};
  nothing may overlap {region}.

## Brand (the only source of color and type: no hardcoded values)

<inline the full tokens.json>
- Follow any contrast/usage notes in the tokens exactly.
- Fonts load from the local files listed in the tokens; no external fonts.

## Look and motion feel (from the Production Bible)

- Feel: {3-5 adjectives from the bible's animation section}
- Overlay aesthetic: {surface treatment, radius, shadow/glow per the bible}
- Ease and duration: tokens motion `easeDefault` for entrances, `easeEmphasis`
  for the hit, `durationBaseMs` for the main move, `durationFastMs` for accents.
- In/out: animate in over {x}ms, hold, resolve out over {y}ms fully inside
  the beat duration (or hold the last frame to a hard cut; pick one).

## Determinism contract (required for rendering)

<the contract above, verbatim>

## Acceptance (machine-verified)

- Frame 0: fully transparent or entrance just beginning.
- Frame at the anchor: key state fully resolved and legible, text verbatim.
- Final frame: fully resolved out (or held) per the in/out spec.
- ffprobe: {fps} fps, {WxH}, alpha present after render.
```

Sources: the approved beat row (timing, anchor, composition), the transcript excerpt verbatim, `{brand-path}/tokens.json` inlined, the Production Bible's aesthetic and motion language, the format profile's safe zones, and the alpha requirement. Timing comes from the beat table and is never invented or stretched by the design; timing changes route back through the creator as beat-table changes.

## The iterate loop

1. Brief: generate the brief file from the beat row, tokens, and the Production Bible.
2. Propose: the design model produces a candidate comp (self-contained HTML honoring the seek contract, authored directly as a HyperFrames comp when it is headed for the engine workspace).
3. Render one frame: seek to the anchor frame and render it, before any video render.
4. Critique against the bible: check the frame against the Production Bible's aesthetic language, the safe zones, the verbatim text, and alpha over checkerboard. Revise and repeat.
5. Review with the creator on a review surface (a Claude Artifact is the worked example) showing the animation looping, a scrub slider driving the same `seek(frame)` the renderer will use, a checkerboard toggle to prove alpha, and a composite over a still frame extracted from the actual footage at the beat's start time, so safe zones are checked against reality. Frame-referenced notes ("at 0:00.8 the underline overshoots") feed the next revision of the local source file, which stays the single source of truth.
6. Render and verify: draft render, then final ProRes 4444, then `{skill-root}/scripts/render_verify.py` (ffprobe pixel format, duration, fps, resolution, extracted frames checked over checkerboard). The verified ProRes 4444 render is the deliverable. A render without checked frames is not done.

## Translating the agreed look into engine code

Once the creator approves the look, it becomes durable engine code rather than a one-off:

- HyperFrames: port the comp into a themed block in the HyperFrames workspace, all colors and fonts read from tokens, timing parameterized so the block can be reused at other durations.
- Foreign HTML exported from a design surface is sanitized before entering a workspace: strip or inline every external reference, replace hardcoded colors and fonts with token references (a grep for hex literals not present in tokens is the lint), retrofit the seek contract, and double-render a frame to verify determinism.
- Record promoted blocks in the format profile's Templates section so future beats assemble them instead of redesigning.

Reusable ffmpeg motion primitives (fly-in and fly-out with optional whoosh, staged infographic builds) live at `{skill-root}/references/motion-recipes.md`; prefer them for simple moves before invoking the full design loop.

## Three traps this lane sets

- A subtle full-frame gradient reads as a design flourish and kills the overlay, because it
  makes every pixel opaque. The checkerboard toggle and the extracted-frame check catch it.
- Models paraphrase text they are asked to render, so read the strings back off the
  anchor frame.
- The hosted preview is never the deliverable. The local frame-stepped render is, and the
  two can disagree.

## Two variants of the brief template

- Multi-anchor beats (a diagram that builds as the speaker names each stage) list every anchor with its timestamp in the Beat block, and their acceptance is a per-anchor frame check: exactly k elements visible at anchor k.
- A HyperFrames stinger brief adds a Deliverables block (ONE comp, TWO renders: ProRes 4444 MOV for the editor, VP9 yuva420p WebM for the live lane) and keeps to 1 to 2 seconds, because transparent WebM renders slowly.
