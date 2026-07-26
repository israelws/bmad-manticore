# Cut Pipeline Remediation Plan

Response to `MANTICORE-CUT-PIPELINE-BUGREPORT.md` (filed 2026-07-24, first real run of Manticore 2.0).

Branch: `fix-cut-pipeline`. Written 2026-07-25 after reading every script in `skills/mc-cut/`, the mc-cut / mc-beats / mc-graphics skills, `PIPELINE.md`, and the artifacts of the project that eventually succeeded (`manticore2/manticore/projects/end-of-code-whats-next/`).

This is a proposal. Nothing has been changed yet.

## 1. Verification: what the bug report got right

Every code-level claim in the report checks out against the source on `main` (97ce6f1). Confirmed with line references:

| Report | Claim | Verified at |
|---|---|---|
| A | parakeet lane never windows | `transcribe.py:243`, bare `model.transcribe(str(media))` |
| A | docstring falsely claims internal chunking | `transcribe.py:71-72` |
| A | the onnx lane windows correctly | `transcribe.py:572-606` |
| C | no transcript validation anywhere | `mc-cut/SKILL.md:17` and the checklist at `:52-57` |
| D | silence comes from transcript gaps | `cutplan.py:131`, `gap = cur["start"] - prev["end"]` |
| E | preview writes the output path directly | `render_preview.py:159-169`, no temp file, no lock |
| E | no output-integrity validation | `render_preview.py:191`, container duration only |
| G | QC frames are extracted, never asserted on | `preflight.py:159-176`, returns paths and nothing else |
| G | no spatial transform exists | EDL segments are `{source, start, end}`; `composite_core.py:209` trims, scales, pads, concats, and never crops |
| 8.3 | no expletive or blooper cues | `cutplan.py:82-88`, `CUE_PHRASES` |
| 8.4 | "so" is blanket-flagged as filler | `cutplan.py:76`, `SOFT_SINGLE` |
| 8.2 | retake window too small for section redos | `cutplan.py:221-242`, `run_min=3` words inside a `window=16` word lookahead |
| B1 | anchor timing is unenforced | `mc-beats/SKILL.md:45`, a checklist line with no script behind it |

## 2. Findings the report did not have

Seven things I found while verifying that change the shape of the fix.

### F1. The two transcription lanes have different gap semantics, and the docstring claims they do not

`transcribe.py:126-130` defines `WORD_END_CAP_FRAMES`, which caps a derived word end at 3 frames past its start specifically so pauses are not absorbed into the preceding word. That protection exists on the onnx lane only. The mlx lane takes parakeet's native token ends, which do absorb pauses (the report's `"about."` spanning 32.16 to 34.64 is exactly this).

So `transcribe.py:37-39` ("The shape is identical across providers; downstream consumers never need to know which lane produced the file") is false in two ways: the mlx lane does not window, and its `gap_before` / `gap_after` mean something different from the onnx lane's. Any silence logic built on gaps is quietly platform-dependent. This is a second reason to move silence detection off the transcript entirely rather than to patch the gaps.

### F2. The "n-now" artifact has a precise root cause

`cutplan.py:200-204`: a stutter candidate's span is `words[i]["start"]` to `words[i]["end"]`, the first occurrence, in transcript time. On the mlx lane that `end` is pause-absorbed, so it sits past the real end of the spoken word and often into the onset of the repeat. Cutting the candidate as emitted clips the second occurrence's attack. That is the audible "n-now" the creator heard, and it is not a taste failure, it is the same timestamp-trust bug as Issue D showing up in a second detector. Silence-anchoring the candidate edges (report §8.5) fixes it structurally.

### F3. Render caching is invested in the wrong renderer

`render_final.py` has content-addressed incremental segment rendering: partition the timeline, hash each segment's inputs, re-encode only what changed. `render_preview.py` has none of that, and it is the renderer that runs after every single cutplan approval and every graphics re-render. The expensive path is cached, the frequently-run path is not. B2's five-hour preview is partly this.

### F4. One audio analysis pass serves both critical fixes

Issue C's murk scan (find no-word spans that are not silent) and Issue D's silence source of truth (find silent spans) are the same `ffmpeg silencedetect` output read two ways. Build one script, `analyze_audio.py`, that emits a silence map once per source, and both the transcript gate and the cut detector consume it. Doing them as separate implementations would run the same expensive decode twice and let the two drift.

### F5. The proposed `editorial` stage collides with a design invariant

`AGENTS.md` lists "Four approval gates (outline, cutplan, beats, final) are hard stops; nothing weakens them" as a settled design invariant requiring maintainer sign-off to change. The bug report's §8.7 asks for a fifth gate between cut and beats.

There is a version that needs no invariant change and is arguably better: run the editorial pass inside the cut stage, after the mechanical EDL is assembled but before gate 2, and present both tiers of calls in one `cutplan.md`. Gate 2 then approves the mechanical trims and the content calls together. This matches what actually happened on the real project only in reverse: there, gate 2 was approved first, the editorial pass ran after, and the EDL had to be rebuilt (`cut/edl.pre-editorial.json` is the scar). Folding it in front of gate 2 removes that rework. See decision D1 in §5.

### F6. Source QC samples two frames and asserts on neither

`preflight.py:164-166` grabs frame 0 and a frame 0.5s from the end. Even with an assertion added, two samples miss a defect that starts mid-take (a frame effect toggled on after recording began). The fix should sample N frames across the duration, not two, and should analyze rather than just write JPEGs.

### F7. The failure pattern behind almost all of this

Four separate defects share one shape: a documented inspection with no mechanical assertion and no exit code.

- QC frames: "inspect the extracted first and last frames for edge defects" (`SKILL.md:16`). Extracted, never inspected, never blocking.
- Boundary frames: "extract frames at each cut boundary and inspect" (`SKILL.md:46`). Extracted, eyeballed, passed while the underlying audio was wrong.
- Transcript: no inspection instruction at all.
- Beat anchors: "every beat has an anchor word that exists in the transcript at that timestamp" (`mc-beats/SKILL.md:45`). A checklist line with no script.

The module's stated design constraint is "taste lives in files, mechanics live in scripts, skills are thin routers." An assertion is a mechanic, not a taste call, and every one of these was left to the agent's judgment. The correction is a rule: any check the skill claims to perform must be a script that exits non-zero. That rule, applied across the four sites above, is the single highest-leverage change in this plan and it is what would have caught the original disaster on minute one.

## 3. Root cause, consolidated

Three architectural mistakes produced every symptom in the report.

1. Transcript timestamps were treated as a timing source of truth. They are a content source of truth. Every timing decision (silence, stutter edges, gap detection) that reads them is wrong on the reference lane. Fix: audio is the timing authority, transcript is the content authority.
2. Verification was advisory. See F7. Fix: assertions in scripts, non-zero exits, halts before downstream work.
3. The cut stage was scoped as cleanup, not editing. The mechanical detector list was treated as sufficient input to a taste gate. Fix: a second tier of detection (silence-anchored, voice-aware, section-scale) plus a content-editorial pass, both feeding gate 2.

## 4. The plan

Eight workstreams. Each names the files it touches and the acceptance test that closes it. Ordering rationale in §6.

### W1. Transcription correctness (Issues A, B, F1)

Files: `mc-cut/scripts/transcribe.py`, `mc-cut/scripts/tests/test-transcribe.py`.

Refactor `transcribe_onnx` into a lane-agnostic `transcribe_windowed(media, recognize_window, window, overlap)` driving the existing `plan_chunks` / `extract_chunk` / `offset_tokens` / `merge_chunk_tokens` machinery, which is already written and already tested. Each lane supplies only a `recognize_window(wav_path, length) -> token dicts` callable.

- The mlx lane's callable loads the model once, calls `model.transcribe(wav)` per window, and maps `AlignedToken` to the token dict shape. `group_subwords` already keys on a leading space in the raw token text, which parakeet emits, so no new grouping logic is needed.
- Window 20s, overlap 3s on both lanes (the report verified 20s; current onnx overlap is 2.0s at `transcribe.py:133`, and 3s costs one extra decode per window while giving the seam-repair pass more to work with).
- Apply the `WORD_END_CAP_FRAMES` discipline to the mlx lane too, or explicitly document that gaps are advisory on both lanes now that nothing downstream depends on them. Prefer the latter, since W2 removes the dependency.
- Fix the docstring at `transcribe.py:71-72` and the "shape is identical" claim at `:37-39`.
- Emit `window_s` and `overlap_s` into the output payload so a transcript records how it was produced.

Acceptance: a 20-minute Apple Silicon transcription exits 0 with no OOM, and produces a word count within tolerance of the 20s-window reference.

### W2. Audio as the timing source of truth (Issues C, D, F2, F4)

New file: `mc-cut/scripts/analyze_audio.py`. Touches `mc-cut/scripts/cutplan.py`, `mc-cut/SKILL.md`.

`analyze_audio.py` runs `ffmpeg silencedetect=noise=-30dB:d=<min>` once per source and emits `cut/audio-map.json`: the silence interval list, total silent seconds, the noise floor used, and a content hash of the source. Two consumers:

1. Transcript completeness gate. New `--verify-transcript words.json` mode (or a separate `verify_transcript.py`, see decision D2) implementing the report's §3 checks: word-rate sanity against `[owner] wpm` (present in `mc-setup/customize.toml:34`), and the murk scan (every inter-word span over 2.5s intersected with the silence map; a span that is not mostly silent is dropped speech). Exits non-zero on failure, names the offending regions with timecodes, and refuses to let the stage proceed.
2. Silence source of truth for `cutplan.py`. Replace `detect_silence`'s gap arithmetic with the audio map, keep the same candidate shape so nothing downstream changes. Add a `--audio-map` argument; when it is absent, fail loudly rather than silently falling back to gaps.

Also in `cutplan.py`: snap every candidate's `start` and `end` to the nearest enclosing silence interval, which fixes F2 structurally and makes the "never cut inside a word" rule mechanically true rather than aspirational.

Acceptance: the broken 3,446-word transcript fails the gate naming the 0:49, 1:27, and 9:37 regions; the good 3,546-word one passes. On the same take the silence detector reports roughly 400 intervals and 300s, not 12.

### W3. Editorial cleanup tier (Issues 8.1 to 8.6)

Files: `mc-cut/scripts/cutplan.py`, `mc-cut/SKILL.md`, `mc-cut/customize.toml`, `mc-setup/assets/voice-bible-spec.md`.

- Dead-air tightening (8.1): a `--tighten-to` pass over the audio map emitting trim candidates for every silence at or above a floor (default 0.45s) down to a target beat (default 0.2s), preserving sub-threshold micro-beats. Both values into `customize.toml` so a studio can tune cadence.
- Section-scale retake detection (8.2): a second matcher alongside `_find_verbatim` with a much longer run minimum and a locality constraint expressed in seconds rather than words, so a genuine section redo is caught in full (first-attempt start to clean-restart start, reset pause included) while a deliberate callback minutes later is not. The existing short-range matcher stays for adjacent stumbles.
- Blooper cues (8.3): expletives and reset phrases as a distinct candidate `type` (not `retake`), scored by proximity to a restart or a long pause so scripted usage is not flagged as a blooper. The vocabulary belongs in `customize.toml`, not hard-coded, since it is per-creator.
- Voice-aware fillers (8.4): remove `"so"` and its cadence-word siblings from the hard-coded `SOFT_SINGLE`. Give the voice bible a machine-readable block (`keep-words`, `cut-words`) specified in `voice-bible-spec.md`, pass its path to `cutplan.py`, and default to cutting hard fillers only. A creator's connective glue is taste, and taste lives in files.
- Stutter resolution (8.5): covered by W2's silence snapping, plus emitting the span of the occurrence to cut rather than a bare first-occurrence window.
- Gate presentation (8.6): `cutplan.md` groups routine trims into one line and itemizes the judgment calls. Already the intent at `SKILL.md:19`; make it explicit that section redos and bloopers are always itemized.

Acceptance: on the real take, full redo spans resolved to the later attempt, the 13:59 blooper flagged, sentence-initial "So" kept, hard fillers cut, stutters silence-anchored.

### W4. Render integrity (Issue E, F3)

Files: `mc-cut/scripts/render_preview.py`, `mc-cut/scripts/render_final.py`, `mc-cut/scripts/composite_core.py`.

- Render to `<output>.<edlhash>.tmp.mp4`, validate, then `os.replace` into place. Atomic on the same filesystem.
- Supersede by content: key the render on a hash of the EDL plus the graphics inputs. A render whose key no longer matches the current EDL when it finishes discards its output instead of publishing it. This is strictly better than process cancellation because it also handles a crashed or detached job.
- Validate before publishing: `ffmpeg -v error -i out -f null -` asserting zero decode errors, plus the existing duration tolerance check. The current check at `render_preview.py:191` reads container duration, which a corrupt file still reports.
- Per F3, give the preview path the same content-addressed segment reuse `render_final.py` already has, or extract that machinery into `composite_core.py` so both share it.

Acceptance: two concurrent renders of the same output yield one valid playable file with zero decode errors, never a corrupt one.

### W5. Preview compositor performance (Issue B2)

Files: `mc-cut/scripts/composite_core.py`, `mc-cut/scripts/render_preview.py`.

The prototype that fixed this live is at `compose_preview.py` in the manticore2 session scratchpad. Two changes, both validated on the real project (about 3 minutes versus an hour):

1. Time-sequential overlay lanes. Pack overlays into the minimum number of non-overlapping lanes by greedy interval scheduling, build each lane as a concat of transparent gaps and overlay clips, then overlay only those lanes onto the base. Depth becomes max concurrent overlays (2 on the real project) instead of total overlay count (56).
2. Preview off a 720p proxy master and 720p overlay proxies. Never re-seek 4K to build a low-res preview.

The prototype hardcodes paths and has no error handling; it is a design reference, not code to lift. Fold the lane-packing into `composite_core.py` so the final render benefits too where its overlay count is high.

Acceptance: a 16-minute cut with 234 segments and 56 overlays previews in single-digit minutes.

### W6. Source QC that halts, and spatial normalize (Issue G, F6)

Files: `mc-cut/scripts/preflight.py`, new `mc-cut/scripts/normalize_source.py`, `mc-cut/SKILL.md`, `PIPELINE.md`.

- Make QC assert. Sample N frames across the duration (not two), detect a uniform-color border ring by edge-variance or ffmpeg `cropdetect`, compare the inferred active-content rectangle against the declared aspect, and exit non-zero with the rectangle reported. Preflight currently exits 0 regardless of what the frames show.
- New `normalize_source.py`: corrective crop to the active-content rectangle, optional recenter, emits a corrected CFR master and reports it for registration as the project source. It touches no timecodes, so an existing transcript, EDL, and cutplan stay valid. That must be stated in the script docstring and in the skill, or an agent will needlessly rebuild them.
- Slot it in `SKILL.md` step 2 (as part of preflight, before transcription) rather than as a new stage, and note in `PIPELINE.md` that corrective normalize is distinct from creative reframing, which belongs to beats.

Acceptance: a source with a baked-in border halts preflight with its active-content rectangle reported; after normalize, the existing EDL and transcript validate unchanged against the corrected master.

### W7. Beat anchor placement gate (Issue B1, F7)

Files: new `mc-beats/scripts/verify_anchors.py`, `mc-beats/SKILL.md`, `mc-graphics/SKILL.md`, `mc-cut/scripts/remap_timecode.py`.

Every beat time must be derived by remapping the anchor word's transcript timestamp through the EDL onto the clean timeline. `remap_timecode.py` already does orig-to-clean mapping, so this is composition, not new math. The new script asserts each beat's anchor word is spoken within a tolerance (default 0.5s) of its start and exits non-zero listing every violation. Wired as a hard gate before any graphics render, per the module's script-duplication convention (the mapping helper gets duplicated into mc-beats).

Acceptance: a beat table with a deliberately mistimed anchor fails the gate and names the row.

### W8. Content-editorial pass (Issue 8.7, and 8.8 as a follow-on)

Files: `mc-cut/SKILL.md`, new `mc-cut/references/editorial-pass.md`, new `mc-cut/assets/editorial-review-template.md`.

This is the one genuinely new capability and the one that is prose, not code. It reads the edited transcript (words.json intersected with the kept EDL segments) against `brief.md`, `script.md`, and the voice bible, and emits a recommendation list under a subtract-only constraint: cut, re-record, generate (consent-gated), hand-to-beats, reorder (gated).

Two things make this tractable rather than hand-wavy:

1. There is already a gold-standard output to template from. `manticore2/.../cut/editorial-review.md` is the artifact this pass produced on the real project, including the caveat block distinguishing high-confidence idea-level findings from `[VERIFY AUDIO]` word-level ones, the priority list, the hand-to-beats seeds, and the applied-changes record. Ship it as the template. Its own postmortem note is the most valuable line in it: most of its source-timecode estimates had drifted to the wrong windows, so a blind apply would have cut wrong spans. That must become a hard rule in the reference: every proposed cut is re-detected against the audio before it is applied, never applied from a transcript-read estimate.
2. Reuse the shipped reviewers rather than reinventing. `bmad-editorial-review-structure`, `bmad-editorial-review-prose`, `bmad-review-adversarial-general`, and `bmad-review-edge-case-hunter` all exist as installed skills. The reference constrains them to subtract-only and maps their findings onto the four operations. Note the module convention that a skill reads only its own folder, so this is a documented invocation, not a file reference.

8.8 (resequencing, highlight and sizzle mining) is real value but is a separate feature on top of a working pass. Recommend deferring it to a follow-on rather than bundling it here.

Acceptance: on a transcript with a planted redundancy, off-goal tangent, contradiction, and misstatement, the pass surfaces each as a gate recommendation with a seam check, applies nothing automatically, and every proposed span is audio-re-detected before application.

### Smaller items

- Issue F (derived-artifact drift): stamp `edl_hash` into `rough.fcpxml`, `cutplan.md`, the boundary frame directory, and the preview, and regenerate all of them together whenever the EDL changes. Falls out of W4's content-keying almost for free.
- Report 9.5 (yt-dlp for published content): guidance only, into `mc-cut/SKILL.md` step 3. Published or on-YouTube source pulls captions with `yt-dlp`; raw local recordings use the windowed local lane; the metered lane stays opt-in. Cheap to write, removes the whole local-ASR failure mode for livestream-vod and footage-first projects.
- `TODO.md` currently claims state as of 1.0.0 and does not mention any of this. It needs a pass at the end.

## 5. Decisions (settled 2026-07-25)

D1. Where the content-editorial pass sits: inside the cut stage, before gate 2. The mechanical EDL is assembled first, the editorial pass runs on the resulting edited transcript, and `cutplan.md` presents both tiers of calls for one gate-2 approval. The four-gate design invariant is untouched, no format profile's `stages` array changes, and the re-cut rework the real project hit (`cut/edl.pre-editorial.json`) does not recur. The bug report's fifth-gate proposal is not adopted.

D2. The transcript gate is its own script, `verify_transcript.py`, consuming the `cut/audio-map.json` that `analyze_audio.py` writes once. Clear contract, clean non-zero exit, one decode.

D3. Scope: all eight workstreams on this branch, one commit, one PR.

D4. Regression fixtures: synthesized for CI (generated audio with known silence patterns and scripted word lists, following the pattern `test-preflight.py` already uses for its integration test), plus a documented manual validation run against the real 20.5-minute take before release. The "known dropped paragraph" case is therefore covered against a synthetic drop in CI and against the real one manually.

## 6. Sequencing and why

W1 before everything, because every other fix downstream of transcription is validated against a transcript, and a broken transcript invalidates the validation. W2 next, because it is the assertion that would have caught the original disaster and because both its consumers block on the same new artifact. W4 next, because a corrupt deliverable at the finish line is the failure that costs the most trust per unit of engineering effort, and it is small.

W3, W5, W6, W7 are independent of each other and can go in any order or in parallel. W7 is the smallest and W5 has the largest wall-clock payoff.

W8 last, because it consumes the edited transcript that W1 through W3 have to be producing correctly first. Running a content-editorial pass on a Swiss-cheese transcript is how this project got here.

## 6a. Implementation record (2026-07-25)

All eight workstreams landed on this branch. Where implementation diverged from the plan above, the reason is here.

New scripts: `mc-cut/scripts/analyze_audio.py`, `verify_transcript.py`, `normalize_source.py`, `edited_transcript.py`, and `mc-beats/scripts/verify_anchors.py`. New references: `mc-cut/references/editorial-pass.md`, `mc-cut/assets/editorial-review-template.md`.

Test counts by suite: analyze_audio 44, cutplan 71, edited_transcript 25, normalize_source 44, preflight 50, render_preview 82, transcribe 68, verify_transcript 32, verify_anchors 40. Every pre-existing suite still passes.

Deviations from the plan:

- W2, the murk scan was inverted. The plan (following the bug report) proposed scanning inter-word spans over 2.5s and testing each for silence. That inherits the bug it is meant to catch, because pause-absorbed word ends make inter-word spans unreliable on the reference lane. The implemented check works from the audio side instead: uncovered speech is the complement of (silence + word spans), so it does not depend on word timestamps being sane at all.
- W2, the word-rate check is much weaker than the report assumed, and this is now pinned as a test (`test_word_rate_alone_would_NOT_have_caught_it`). Three missing paragraphs are a 3 percent word deficit in a 20 minute take, so the broken transcript reads 224 wpm against the good one's 231. The report's proposed 55 percent floor would have passed it. The rate check ships because it catches catastrophic failure (a truncated file, a wrong-language model), but the coverage scan is the only thing that catches dropped paragraphs, and the docstring says so.
- W3, silence candidates changed meaning. A candidate's span is now the part to REMOVE rather than the whole silence, which makes every candidate type mean the same thing. The dead-air tightening from 8.1 falls out of this rather than being a separate pass.
- W4, `nearest_silence` needed a direction parameter. Unconstrained nearest-silence snapping can pull a candidate's end backwards past its own start and annihilate it. Starts snap back, ends snap forward, so a span can only widen into silence.
- W4/F3, preview segment caching was NOT implemented, deliberately. W5's proxy masters make a full preview render cheap enough that incremental segment reuse would add cache-invalidation complexity for little gain. Revisit only if a real project shows preview renders still slow after proxies.
- W5, lane intermediates default to qtrle rather than the prototype's ProRes 4444. Both carry alpha, but qtrle run-length encodes flat transparency, and an overlay lane is mostly transparent; ProRes would write gigabytes of temp per lane on a long video. `--lane-codec prores` keeps the validated original available.
- W6, QC needed a false-positive guard the plan did not anticipate. A flat border is not enough on its own, because a genuinely dark or flat scene has uniform edges too. The border must also be colour-distinct from the picture inside it. QC halts and asks rather than auto-cropping for the same reason.
- W8, `edited_transcript.py` was added (not in the plan). The editorial pass needs the edited transcript as a real artifact with dual timecodes, and generating it by hand is precisely where the first editorial pass went wrong.

### Threshold calibration against the real take (2026-07-25)

The release-gate manual validation in TODO.md was run early, because the first-pass thresholds were guesses and the real footage was available. `raw/master-normalized.mp4` from the reference project plus its known-good (3,546 word) and known-broken (3,446 word) transcripts settled four of them. Results:

- The gate FAILS the broken transcript (exit 1) naming five dropped regions at 0:49, 0:56, 1:27, 2:36 and 9:37, and PASSES the good one (exit 0) with zero false positives across 20.5 minutes. The three regions the bug report named are all caught; 0:56 and 2:36 are ones it never found.
- `word_rate.ok` is TRUE on the broken transcript, confirming on real data what §2 predicted from arithmetic: the rate check would not have caught this.
- Dead-air floor moved 0.45 to 0.30 (87 percent of trimmable dead air to 99 percent, about 29 seconds per 20 minutes).
- Dropped-speech threshold moved 2.5 to 1.0 (zero false positives measured all the way to 0.75; 2.5 was missing a real region).
- Audio map granularity moved 0.3 to 0.10, since the map must be finer than every consumer and edge snapping needs the 0.1 to 0.2s gaps.
- Blooper context tightened from "0.5s pause within 3s" to "2.0s stop within 1.5s", because the loose version classified the scripted "that damn term" as a near-certain flub. Measured separation: 0.77s beside the scripted line, 7.65s beside the real one.

The detector also independently found the "Oh fuck." at 13:59 and a 33.3s section re-read at 13:36; the bug report says the old detector undersized that same redo from about 34s to about 11s.

Two bugs were found by the new tests rather than by reading, both worth recording because they are the same class as the one being fixed:

- `render_preview.py` computed its overlay digests from `ov["file"]`, but the overlay dict key is `path`. `content_digest` returns "missing" for an absent path, so every overlay hashed identically and the render key would not have changed when a graphic was re-rendered. Caught by wiring W5 through the key.
- Two concurrent renders built the same preview proxy path and interleaved writes into it, which is exactly the corruption the workstream exists to prevent, one level down. Caught by the concurrency test flaking, not by review. Proxies now stage and atomically publish like deliverables. `write_json_atomic` was added for the same reason after the test exposed torn EDL reads.

## 7. What this does not address

- The report's §8.8 (resequencing, sizzle mining). Deferred by recommendation, not by oversight.
- Multitrack and multicam, already on `TODO.md`, unaffected by any of this.
- The onnx lane's real-hardware validation on Windows and Linux, already on `TODO.md`. W1 changes shared code, so that validation becomes more urgent, not less. Worth a line in `TODO.md`.
