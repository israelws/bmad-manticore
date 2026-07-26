# Source preparation

Everything between a file landing in `raw/` and it being safe to transcribe or
cut. Load this when preflight reports a problem, or when a source needs a
spatial fix.

`uv run {skill-root}/scripts/preflight.py raw/<take> [...] --remux --qc-frames cut/qc/`

Run it on every source before anything else. It is slow on large files, so start
it in the background and let transcription wait on it.

## What it checks

| Check | Failure | What to do |
|---|---|---|
| Frame rate | VFR source | `--remux` re-encodes to constant frame rate and reports a `cfr_master` path |
| Disk | `disk.ok` false | Stop and tell the creator. The script refuses the remux itself rather than filling the disk |
| Source QC | exit 3 | Hard stop. See below |
| Duration and streams | probe failure | The file is unusable; get another export |

The disk estimate is rough (about 3x source size plus the estimated CFR
masters). It is a floor, not a guarantee, so a render can still run tight on a
nearly full volume.

## The CFR master replaces the original

Record the reported `cfr_master` in `project.json` `sources`. Every later step
(transcription, EDL times, renders, timeline export) reads that path, never the
VFR original. The two files have different frame timing, so mixing them
desynchronizes the FCPXML export in a way that looks fine until the creator
scrubs the timeline in their editor.

## Source QC exit 3

The script samples frames across the take and asserts on them, exiting 3 on a
flat decorative border ring, or an active area whose aspect does not match the
container. Report the inferred active-content rectangle and get the creator's
call. Do not transcribe, cut, or render against a source that failed QC.

Two ways forward, and they are different decisions:

The framing is a defect. Crop it out:

```
uv run {skill-root}/scripts/normalize_source.py raw/<take> \
    -o raw/<take>-normalized.mp4 --auto \
    [--offset-x N] [--target-aspect 16:9] [--output-size WxH]
```

Register the corrected file in `project.json` `sources` as the new
`cfr_master`. This must happen before the beats and graphics stages, because
overlays are positioned against the canvas.

A spatial crop moves nothing in time. The script asserts the duration is
unchanged and refuses to publish otherwise, so an existing transcript, EDL,
cutplan and beat table all stay valid. Do not re-transcribe and do not re-cut
after a normalize.

The framing is intentional. Re-run preflight with `--allow-qc-defects`. This is
a recorded override, so get the creator's confirmation first.

Keep both distinct from creative reframing (punch-ins, motion zooms), which
belongs to the beats stage working on an already-clean canvas.
