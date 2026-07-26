# Skill scan actions (2026-07-25)

What to do about the 36 findings from the quality scan of `mc-cut` and `mc-beats`.
Report: `skills/mc-cut/.analysis/2026-07-25-1758/skill-analysis-report.html`.

## The organizing rule

This branch's job is the cut-pipeline remediation. So the split is:

A finding lands in THIS commit when the branch itself introduced the defect, or when
the branch now ships a claim that is false. Everything else is a follow-up PR, because
mixing a structural rewrite into the remediation diff makes both unreviewable.

That rule puts 11 items in this commit and 13 in follow-ups, and rejects 2.

## Status: bucket A is complete (2026-07-25)

All 11 items landed. 899 tests green, up from 824. Both new scripts were also
run end to end against real ffmpeg output, not just unit fixtures.

Two things to know before the commit:

- `mc-cut/SKILL.md` grew from 4,492 to 4,942 tokens. Bucket A added a gate step
  and the gate table, so the file got further over budget, not closer. F1 (the
  carve) is now the more urgent follow-up, not a nice-to-have.
- Writing the gate turned up a design trap worth recording. The obvious
  implementation of "never cut inside a word" fails CORRECT cuts: a
  pause-absorbed word end reaches past the sound, so a boundary correctly
  placed in silence sits inside the word's timestamp span. The gate therefore
  treats the audio as the authority and word overlap as context on an
  already-failing boundary. A test pins the exact case.

## Bucket A: must land before commit

These are defects this branch created, or claims this branch makes that are not true.

| # | Action | Findings | Size |
|---|---|---|---|
| A1 | Write `mc-cut/scripts/verify_edl.py`, wire as hard stop after steps 6 and 7a, add to PIPELINE.md gate table | determinism-1 | new script + tests |
| A2 | Shrink the Self-verify contract to a true four-gate list once A1 exists | architecture-2, leanness-1, enhancement-5 | prose |
| A3 | Point `mc-beats` at `verify_anchors.py` instead of the nonexistent step 6a | architecture-4, leanness-7 | one line |
| A4 | Delete the dead `re` import in `verify_anchors.py` | determinism-6 | one line |
| A5 | Add `cut/editorial-review.md` to mc-beats step 1 read list and step 2 riff input | architecture-3, enhancement-4 | two lines |
| A6 | Complete PIPELINE.md stage 6 artifact row (`edl.pre-editorial.json`, normalized master, preview key sidecar) | architecture-7 | one row |
| A7 | Stop `cutplan_flags` reaching `-o` / `--audio-map` / `--voice-bible` | customization-1 | see below |
| A8 | Give the transcript gate a real recovery or an honest one | enhancement-3 | small |
| A9 | Say plainly that RE-RECORD pickups are handled outside the pipeline | enhancement-1 | one clause |
| A10 | Rename `analyze_audio.py --min-silence` to `--map-granularity` | customization-6 | one flag |
| A11 | Expose the noise floor as a config value | customization-4 | small |

### A1 is the critical one

`cut/edl.json` is hand-authored at step 6 and rewritten at 7a, and no script ever reads
it back. Verified by grep: only `cutplan.py` and `verify_transcript.py` consume the audio
map. So both non-negotiable cutting rules and two checklist lines have zero enforcement,
while `AGENTS.md` now makes it binding that a claimed check is a script that exits non-zero.

`verify_edl.py` takes `cut/edl.json` + `transcript/words.json` + `cut/audio-map.json`,
all of which already exist on disk, and exits 1 on:

- a segment boundary inside a word span
- a boundary not resting inside an audio-verified silence, reporting the miss distance
- a segment missing `quote` or `reason`
- times out of order, or outside `source_duration`

Every one of those is deterministic and unit-testable, which is exactly why none of them
belong in a checklist line. This is the same shape as `verify_anchors.py`, which this branch
already wrote for `mc-beats`. mc-cut simply never got its twin.

Worth folding in: expose `snap_candidates` as a CLI on the same script (determinism-2), so
step 7a stops asking the model to snap edges into silences by hand. Same file, same inputs,
and it removes the one remaining place where the branch asks for arithmetic in prose.

### A2 resolves a disagreement between two lenses

Leanness says delete the Self-verify section as a third telling. Determinism says make its
claim true. Both are right about the current text being wrong.

Resolution: once A1 exists there really are four mechanical gates, so the section becomes
true. Shrink it to the four gate names and their exit codes, delete the three bullets that
restate steps 2, 3b and 8 in full, and demote the by-ear seam listen to what it is, a human
confirmation carried in the Checklist rather than counted as one of the four.

### A7 is a correctness hole, not a style point

`SKILL.md` appends `{workflow.cutplan_flags}` AFTER the skill's own arguments, and argparse
lets a later occurrence win. An override file containing `--audio-map` silently swaps the
timing source of truth this branch just established. `customize.toml` asserts that boundary
in a comment with nothing enforcing it.

Minimum fix for this commit: have `cutplan.py` reject `-o`, `--audio-map` and `--voice-bible`
when they arrive twice, exiting 2. That closes the hole without redesigning the surface.
The full typed-key redesign is F7 below.

### A8: pick one

The gate prescribes "re-transcribe those regions in isolation and splice". Verified:
`transcribe.py` has no region flags and no splice utility exists, so the prescribed recovery
cannot be performed. And unlike `preflight` (`--allow-qc-defects`), the gate has no override,
so a laugh or a music bed above the floor blocks a run permanently.

Cheapest honest option: add `--accept-region <start>-<end> --reason <text>`, recorded in
`transcript-check.json`. Keeps the gate blocking by default, gives it the same escape valve
preflight already has. Preferred option if there is appetite: `--start/--end` on
`transcribe.py` plus a splice mode, which makes the prescription real.

## Bucket B: cheap, worth taking in the same commit

| # | Action | Findings |
|---|---|---|
| B1 | `# noqa: E402` on the seven shim imports, plus a line in AGENTS.md naming the shim as sanctioned | determinism-7 |
| B2 | Add the routed-re-entry clause to PIPELINE.md's stage algorithm | architecture-6 |
| B3 | State render-flag precedence: studio config first, `*_flags` as escape hatch | customization-5 |
| B4 | Cut the 2026-07-24 retellings from four to one, and drop caps except on the two hard stops | leanness-5, leanness-6 |

B1 matters more than it looks. Right now eight sanctioned shim imports lint as high-severity
E402, so a genuine import-ordering bug in a future edit is indistinguishable from them, and
every future scan re-litigates the same eight.

## Bucket C: follow-up PRs

Real findings, deliberately not in this commit.

| # | Work | Findings | Why not now |
|---|---|---|---|
| F1 | DONE 2026-07-25. Rewritten to the builder's canon, not carved. 4930 to 2353 tokens. See `F1-CARVE-PLAN.md` | architecture-1, architecture-5, leanness-2, leanness-3, leanness-4 | Was: a structural rewrite of the file this branch is already changing heavily. |
| F2 | Resume by artifact: source digest in `audio-map.json` and `words.json`, resume clause in step 1 | enhancement-2 | New capability. Genuinely valuable on a stage whose first four steps cost tens of minutes. |
| F3 | Persist gate 2 decisions to `cut/decisions.json`, `--decisions` flag on cutplan | enhancement-6 | New capability. Fixes real re-litigation on the second cut pass. |
| F4 | Extend `verify_anchors.py` with the five countable beat-table quotas | determinism-3 | Expands a script that currently works and is unreleased. Better as its own change. |
| F5 | `check_derived.py` or `--check-only` for derived-artifact staleness | determinism-4 | The checklist currently asks the model to compare two digests it cannot compute. |
| F6 | Assert on black boundary frames instead of only extracting them | determinism-5 | Same defect class as the QC frames this branch fixed, one level down. |
| F7 | Replace `*_flags` strings with typed keys the resolver merges by key | customization-1 | The full redesign. A7 closes the dangerous half now. |
| F8 | Move marker cue to per-source metadata in `project.json` | customization-2 | Touches mc-setup and the project.json schema. |
| F9 | Move blooper vocabulary into the voice bible next to the cadence block | customization-3 | Touches the mc-setup asset spec. Right call: two per-creator speech vocabularies should not have two homes and two merge semantics. |
| F10 | Add `on_complete = ""` module-wide | customization-7 | Verified missing from all 16 skills. A module-wide sweep, not an mc-cut fix. |
| F11 | Implement the pickup re-entry loop properly as step 7b | enhancement-1 | A9 tells the truth now; this builds the capability later. |

## Rejected

Two recommendations I do not think we should take.

- Raising mc-cut's SKILL.md budget to 3500 (leanness-8). This rationalizes the overage.
  About three quarters of the 4492 tokens is friction by that lens's own measurement, so the
  answer is F1, not a higher ceiling. Revisit only if the carve lands and the file is still over.
- Scaling the editorial pass down on short pieces (enhancement-7). The pass was deliberately
  placed inside the cut stage before gate 2 and has never run on a real project. Adding a
  conditional before we have usage data optimizes a cost nobody has measured yet.

## What the scan confirmed is working

Worth recording so a later pass does not flatten it:

- Thresholds calibrated against the real 20-minute take, with the sweeps in the repo.
- The two-source rule enforced structurally, not asserted: `--audio-map` required with no
  gap fallback, plus a regression test pinning the real 0.0-gap case.
- The taste and mechanics split inside `cutplan.py`.
- `verify_anchors.py` re-derives independently rather than checking the model's own arithmetic,
  and deliberately does not snap a missing anchor to the nearest match.
- The Checklist. It looks like duplication but every line names a script and an exit code,
  and it is what gets re-read after the steps scroll out of context.

## Housekeeping

`skills/mc-cut/.analysis/` is untracked and will land in the PR unless it is gitignored or
removed before commit.
