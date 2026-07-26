# F1: rewrite mc-cut/SKILL.md to the builder's canon (2026-07-25)

Supersedes the first version of this plan, which benchmarked mc-cut against its
sibling skills. That was the wrong ruler. The bar is
`.claude/skills/bmad-workflow-builder/references/prompt-quality-canon.md` plus
`references/skill-quality-principles.md`, and measured against it the siblings
fail too.

## What I got wrong the first time

My first plan proposed reorganizing the thirteen numbered steps into four named
phases with the gate stops made visually explicit. That is still writing the
route. It is a tidier script of one imagined good session.

The canon names this exact instinct as the defect it exists to prevent:

> Asked to build a prompt, you will script the path, phased sequences, question
> banks, templates with mandatory sections, because elaborate scaffolding feels
> like diligence and reads like quality. That instinct is the central defect
> this canon exists to prevent.

And `standard-fields.md` is explicit that numbered stages are the wrong form at
all: "a number implies a fixed order the model must march through and fights the
outcome-driven shape."

So this is not a carve. It is a rewrite from the destination, keeping the
non-inferables.

## Measured against the real budget

Tokens via the builder's own `scripts/count_tokens.py`. Desired 2000, hard 3000.

| Skill | Tokens | Tier |
|---|---|---|
| mc-setup | 6060 | over budget |
| mc-cut | 4930 | over budget |
| mc-package | 3385 | over budget |
| mc-agent | 2687 | warn band |
| mc-beats | 2460 | warn band |

Three skills are over the hard budget and two more are in the warn band. mc-cut
is the second worst, not the worst.

Two conventions fail module-wide, not just in mc-cut:

- `## Resolution rules` block: required in any SKILL.md referencing multiple internal files. Present in 0 of 16.
- Description format (`[5-8 word summary]. [Use when the user says 'phrase'.]`, triggers quoted): mc-cut's is 49 words with no quoted trigger. 9 of 16 carry no quoted trigger at all.

## Defects in mc-cut, against the canon

### C1. The destination is never stated

The canon's shape is stance, outcome, consumer, bar, non-inferables. It calls
the consumer "the highest-leverage line in any prompt, because completeness,
rigor, and tone all derive from it."

mc-cut states none of them. Its opening paragraph is a feature list that
restates the frontmatter description. And mc-cut has three distinct consumers
that would each set a real bar if named:

| Consumer | The bar it sets |
|---|---|
| The creator at gate 2 | Can say yes or no to every taste call without re-watching the raw footage |
| The creator's NLE | Imports the timeline and stays in sync |
| mc-beats | Builds visuals against the edited transcript and the editorial review |

Naming those three replaces a good deal of the prose that currently tells the
model how thorough to be.

### C2. Thirteen numbered steps, six of them letter-suffixed

The sequence is 1, 2, 3, 3a, 3b, 4, 5, 6, 6a, 6b, 7, 7a, 8. The letters are an
insertion changelog. Canon test 5 says number only true sequences; some of these
genuinely feed each other and the dependency is real, but the fix per
`standard-fields.md` is descriptive stage names with the dependency stated in
prose, not tidier numbers.

Step 5 is the clearest case: "pick best takes, order segments, decide keep-or-cut"
is a goal wearing a step's clothes, and it is exactly what a capable model does
unprompted once it knows the outcome and the consumer.

### C3. Roughly 600 words of mechanics living in the wrong file

The canon says to cut "mechanics that belong in the file that performs them."

| Line | Words | What it is |
|---|---|---|
| 46 | 218 | Per-OS hardware encoder ladder, segment cache internals, two-pass loudnorm. This is `render_final.py --help`. |
| 18 | 152 | CUDA escalation and PEP 508 marker rationale. This is the `transcribe.py` docstring. |
| 17 | 126 | normalize_source usage plus the duration-invariance argument. |
| 37 | 78 | An entire bullet about a stub, with per-OS Fusion Scripts folder paths for a feature that does not exist. |

### C4. Negative space

The canon cuts "negative space (what this no longer does)". mc-cut narrates
absence in at least three places: the resolve_import stub bullet, the xmeml and
edl "planned lanes", and "there is no pickup re-entry path in the pipeline yet".

### C5. The same fact told three to five times

| Fact | Told at | Times |
|---|---|---|
| Never cut inside a word, snap to silence | L25, L31, L55, L80, L82 | 5 |
| The composited preview re-render | L8, L12, L34, L42 | 4 |
| The preview renders after every approval | L8, L33, L42, L84 | 4 |
| Boundary frames extracted and inspected | L33, L74, L84, L86 | 4 |
| verify_edl.py is a hard stop | L27, L69, L81 | 3 |
| verify_transcript.py is a hard stop | L22, L68, L79 | 3 |
| The two-source rule | L21, L54 | 2, near verbatim |

The pattern is worth naming: the worst offenders are the rules this branch cared
most about. Each new safety rule got asserted in its step, again in the cutting
rules, again in the self-verify section, and again in the checklist. Conviction
became repetition.

### C6. The Checklist is the Steps again

Nine bullets, about 340 words, six of which restate a script the gate table
already covers. I defended this list in `SKILL-SCAN-ACTIONS.md` as what gets
re-read after the steps scroll out of context. That defense was right before A1
and wrong after it: now that all four gates exit non-zero, a model cannot skip
them by forgetting, because the script fails. Only what no script can check
survives.

### C7. Path convention

17 uses of the `{skill-root}/` prefix where the convention is bare paths from
the skill root. Minor in isolation, but it is pure prefix on every command.

## The target shape

Destination first, then the non-inferables, then the wiring. Estimated 1500 to
1900 tokens, inside the desired tier rather than merely under the hard budget.

Concrete draft of the opening, so the target is judgable rather than described:

```markdown
---
name: mc-cut
description: Cut raw takes into an approved, rendered edit. Use at the cut
  stage, or when the user says "cut this", "make the cutplan", or "render the
  preview".
---

# mc-cut

Act as the creator's editor. The outcome is an approved cut: `cut/edl.json` and
the preview, cutplan, editorial review and editor timeline built from it. Three
consumers set the bar. The creator at gate 2 must be able to accept or reject
every taste call without re-watching the raw footage. Their NLE must import the
timeline in sync. mc-beats builds visuals on the edited transcript and the
editorial review, so both must be true before this stage closes.

This stage owns two of the four gates: gate 2 on the cutplan, and the offered
final render at gate 4.

One rule is not inferable and cost a real project on 2026-07-24. The TRANSCRIPT
is the authority on CONTENT; the AUDIO is the authority on TIMING. parakeet
absorbs pauses into the preceding word's end, so transcript gaps read about 0.0
across real dead air. Never derive a cut time, a beat time, or a silence from
transcript timestamps.
```

That is the whole current opener, the two-source rule, the gate ownership, and
the consumer bar, in fewer tokens than the current opener plus its duplicates.

### What stays in SKILL.md as non-inferable

The canon keeps persona, wiring, institutional knowledge, and rules with real
consequences. For mc-cut that is:

- The two-source rule, with its why. Non-obvious and expensive.
- The 20s windowing invariant, with its evidence. A model would optimize this away precisely because it looks like a tuning knob.
- The exact script invocations. The canon reserves exact procedure for "operations where a wrong move actually costs something", which is every gate here.
- The four-gate contract and the rule that a claimed check is a script that exits non-zero.
- The CFR master as the source of truth for every downstream step.
- Never shrink or letterbox the frame for graphics.
- Gate 2 and gate 4 as hard stops.

### What moves to references

One level deep, each standalone, routed by name from SKILL.md.

| File | Absorbs |
|---|---|
| `references/source-prep.md` | Preflight's four checks, QC exit 3, normalize_source, disk gate |
| `references/transcription.md` | Provider lanes, CUDA escalation, the yt-dlp caption lane, provenance |
| `references/rendering.md` | Preview and final invocations, encoder ladder, segment cache, loudnorm, flag precedence, timeline-format lanes |
| `references/editorial-pass.md` | Unchanged |

### What is deleted

C4 and C5 in full, plus C6 down to the three items no script can check:
listening at the joins, FCPXML sync on first use of the converter, and unsnapped
spans checked by ear.

## Method

The risk is that a rewrite quietly drops a line somebody bled for, and this file
is full of lines that exist because a real project broke. So:

1. Every sentence in the current 86 lines gets classified as kept, moved to a named reference, or deleted with the surviving citation recorded. That mapping lands in this file before any edit, so deletions are reviewable as a list rather than hunted in a diff.
2. The AGENTS.md invariants get checked one by one against the result. Several of them, the windowing rule, the two-source rule, atomic writes, four gates, are exactly the facts most at risk in a compression pass.
3. No script changes. The 899-test suite is not the safety net here and is not being asked to be.

## Result (2026-07-25)

SKILL.md went from 4930 tokens to 2353, a 52 percent cut, 86 lines to 131. Under
the 3000 hard budget. Still above the 2000 desired tier, so it sits in the warn
band rather than on target; see "What I did not get to" below.

| Check | Result |
|---|---|
| `count_tokens.py` SKILL.md | 2353, under the 3000 budget |
| `quick_validate.py` | ok, no errors |
| `scan-path-standards.py` | 3 findings, all inside the gitignored `.analysis/`, none in shipped files |
| `lint_genericity.py` on the 4 new/rewritten files | clean |
| mc-cut test suite | 597 passing, 0 failing. No script changed |
| Invariant survival grep | all 24 tracked terms still present |
| Cross-file references | no file outside mc-cut cites its step numbers; all cross-refs are by artifact path or script name, both preserved |

### Disposition of every section

| Old lines | Content | Disposition |
|---|---|---|
| 1 to 4 | Frontmatter | Rewritten: 8-word summary plus quoted trigger phrases |
| 6 to 8 | H1 and opener | Replaced by the destination paragraph: stance, outcome, three consumers, both gates |
| 12 | Config load | Kept, split into On Activation 1 to 3 |
| 13 to 17 | Preflight, four checks, normalize | Command, the CFR gotcha and the exit-3 trigger kept; detail to `references/source-prep.md` |
| 18, 20 | Transcribe, lanes, CUDA, captions | Lane choice to `references/transcription.md`; the windowing invariant kept in SKILL.md as a gotcha |
| 21 | Audio map, two-source rule | Command kept; the rule lifted into its own section at the top |
| 22, 24 | Transcript gate, accept-region | Gate kept; override detail to `references/transcription.md` |
| 25 | cutplan.py | Command kept; the cadence and interview-marker gotchas compressed but kept; the detector list cut (the script reports it) |
| 26 | "Make the taste calls" | Folded into one clause. It was a goal wearing a step's clothes |
| 27, 28, 31 | verify_edl, edited_transcript, apply and snap | Kept close to verbatim. These are gates and exact invocations |
| 29 | Editorial pass | Compressed to the two gotchas (nothing auto-applied, RE-RECORD exception); the rest already lives in `references/editorial-pass.md` |
| 30 | cutplan.md and gate 2 | Kept, compressed. The "itemize what they might disagree with" instruction now derives from the stated consumer bar |
| 32 to 38 | Step 8, six bullets | To `references/rendering.md`. Deliver keeps the goal, the boundary frames, and the state advance |
| 40 to 46 | Composited preview and final render | To `references/rendering.md`; one line each under Routed re-entries |
| 48 to 50 | Dual timecode | Kept inline. Too small to repay the indirection |
| 52 to 59 | Cutting rules | Six to three. Dropped "never cut against VFR" and "every segment records quote and reason", both stated in their own section and enforced by a gate |
| 61 to 74 | Self-verify contract | To the Gates table plus the three human-only items |
| 76 to 86 | Checklist | Deleted. Its three irreplaceable lines survive under Gates |

### Deletions, with the surviving citation

| Deleted | Survives at |
|---|---|
| Composited re-render, 3 of 4 tellings | Routed re-entries |
| Preview renders after approval, 3 of 4 | Deliver |
| Boundary frames, 3 of 4 | Deliver |
| The 2026-07-24 postmortem, 2 of 3 | The windowing paragraph, with one back-reference clause at boundary frames |
| Two-source rule, 1 of 2 | Its own section |
| resolve_import per-OS Fusion Scripts paths | One line in `references/rendering.md` naming it a stub, because the file exists and reads as usable |
| "Planned lanes" narration | One table row in `references/rendering.md` |
| Encoder ladder, segment internals, CUDA rationale | The relevant reference, and each script's own docstring |

### What I did not get to

2353 is under budget but above the 2000 desired tier. Getting there means moving
the interview-marker branch and the editorial-pass gotchas into references, which
would save roughly 150 tokens and break the principles' own rule that a gotcha
the model cannot recognize the trigger for stays in SKILL.md. I stopped rather
than trade a real safety property for a number.

One pre-existing issue surfaced and was left alone: `lint_genericity.py` flags 5
brand-term findings in `references/editorial-pass.md`, which name actual BMad
skill names (`bmad-editorial-review-structure` and siblings). They predate this
work and are arguably false positives for a module that is itself BMad, but the
release gate does not know that.

## Module-wide

The same treatment applies to mc-setup (6060 tokens), mc-package (3385), and the
two in the warn band, plus the Resolution rules block and the description format
across all 16. Out of scope for F1, worth its own pass.
