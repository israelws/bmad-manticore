# Rendering and export

The preview render, the gate-4 final render, and the editor timeline export.
Load this when rendering or exporting. Full flag lists live in each script's
docstring; this file carries the wiring and the decisions.

## Where encoder settings live

The studio config is their single home. Emit the `[render]` and `[video]` keys
first, then `[cut] preview-flags` or `[cut] final-flags` last.

Because the last occurrence wins, restating a key the config owns inside a flags
string silently overrides it, and which value applies then depends on emission
order rather than on any stated rule. So the flags strings are an escape hatch
for what the config does not model, such as `--segment-target-seconds`. Never
put `--height`, `--crf`, or the loudness flags in them.

## Preview

```
uv run {skill-root}/scripts/render_preview.py cut/edl.json \
    -o renders/preview.mp4 --boundary-frames cut/boundaries/ \
    plus [cut] preview-flags
```

Defaults to 720p CRF 28 when `[render]` leaves them unset. Never
loudness-normalized. Check `"validated": true` in the summary.

Composited, once the graphics stage has rendered overlays into `graphics/`, add:

```
--beats beats/beats.md --graphics-dir graphics/
```

Report any `overlays_missing` from the summary; each one is a beat whose overlay
has not landed in `graphics/`.

## Final render, offered at gate 4

```
uv run {skill-root}/scripts/render_final.py cut/edl.json \
    -o renders/final.mp4 --beats beats/beats.md --graphics-dir graphics/ \
    plus [cut] final-flags
```

Wire the config in: `--codec` and `--crf` from `[render]`, `--height` from the
height of `[video]` delivery-resolution, `--loudness-target` from `[render]
loudness-target`, and append `--no-loudnorm` when `[render] loudnorm` is false.

It bakes the same EDL the creator approved, with graphics composited from the
approved beat table. Finishing in the creator's own editor from the always
exported timeline is an equally supported path; either closes gate 4.

What the script handles without instruction: hardware encode selection with a
one-frame test encode per candidate and an libx264 fallback, a disk preflight,
progress reporting, boundary-frame checks, and two-pass loudnorm when enabled.

Persistent incremental segments are worth knowing about, because they change
what a re-render costs. The timeline is partitioned into content-addressed
segments under `renders/segments/`, and a re-render re-encodes only the segments
whose inputs actually changed. A single tweaked graphic on a long video is a
seconds-long re-render, so re-rendering after a small fix is cheap and there is
no reason to batch changes to avoid it. `--segment-target-seconds` (default 600)
tunes segment size.

## Editor timeline export

Always exported, per `[editor] timeline-format`.

| Value | Command | Notes |
|---|---|---|
| `fcpxml` | `uv run {skill-root}/scripts/edl_to_fcpxml.py cut/edl.json -o cut/rough.fcpxml` | Resolve and Final Cut import it natively. Refuses VFR sources loudly |
| `xmeml`, `edl` | Not yet implemented | Premiere users work from cutplan.md, edl.json and the rendered preview. See TODO.md |
| `none` | Skipped | Descript and manual workflows. The deliverables are cutplan.md, edl.json and renders/preview.mp4 as the cut map |

`{skill-root}/scripts/resolve_import.py` is a stub. Do not offer it. It is named here only
because the file exists and reads as usable; when its STATUS line says
implemented, offer it only where `[mcp] davinci-resolve` is true.

## Derived artifacts drift silently

The EDL is the single source of truth. The preview, the boundary frames, the
timeline export and cutplan.md are all derived from it, and nothing stops an
older one sitting next to a newer EDL looking current.

The preview writes an `<output>.key` sidecar naming the render identity it was
built from. When that key does not match the current EDL's, the derived set is
stale and all of it regenerates together.
