# The editorial pass

The cut stage has two tiers. The mechanical tier (`cutplan.py`) makes the take clean: dead air, stutters, fillers, redos, bloopers. This pass makes the video better. It reads the delivered piece as an argument and asks the question no mechanical detector can: should this section exist at all?

Both tiers feed one gate. The creator approves the mechanical trims and the content calls together at gate 2.

## The constraint that defines it

You can only subtract.

This is not editing a document. The words are recorded audio in the creator's voice, so there is no rewriting a clumsy sentence and no adding a clarifying clause. Every recommendation resolves to one of five operations:

| Operation | What it means | When |
|---|---|---|
| CUT | Remove a spoken span | Redundant, off-goal, or clearly weak, and the seam still reads |
| RE-RECORD | Flag a creator pickup | Load-bearing but wrong; the only true way to fix or add |
| HAND TO BEATS | Do not cut; solve it visually | Thin or confusing but fixable with a diagram, overlay, or punch-in |
| GENERATE | Synthetic-voice fill, consent-gated | Tiny bridges only, and never without explicit consent; it fabricates the creator's voice |
| REORDER | Move a self-contained span | Propose only, never auto-apply; risk scales with format (see below) |

Because it is subtractive, every proposed cut carries a seam check: the confirmation that the audio still reads grammatically and logically once the span is gone. You cannot rewrite the connective tissue, only remove whole spoken spans, so a cut that leaves a broken join is not a cut you can make. That seam constraint is exactly what separates this from prose editing.

## When it runs, and why the placement is load-bearing

Inside the cut stage, after the mechanical EDL is assembled, before gate 2.

It reads the EDITED transcript, `cut/edited-transcript.md` from `edited_transcript.py`, which is `words.json` intersected with the kept EDL segments. Not the script, and not the raw transcript:

- The script is what was planned. Delivery diverges from it: ad-libs, dropped lines, live rewrites, and the strongest findings are often about ad-libbed content that was never in the script at all.
- The raw transcript still contains everything the mechanical pass removed, so a pass reading it reviews words the viewer never hears.

Content is cheapest to change before you decorate. If this pass recommends cutting a section and beats has already built an overlay and a punch-in for it, that visual work is dead and beats must be re-planned. Settle what stays before spending effort on how it looks. Re-record flags loop back through the cut, and beats plans against the final cut, so pickups must land first.

This pass is never a separate stage and never adds a fifth gate: four gates is a settled invariant, and folding the pass in front of gate 2 removes rework rather than adding a stop. Approving gate 2 before this pass runs forces a rebuild of the approved EDL.

## What it hunts for

1. Redundancy. A point already made, restated with no new value. Conceptual, not verbatim: the mechanical retake detector cannot see it because the words differ. Respect deliberate repetition. Callbacks, rule of three, anadiplosis, and the intentional emphasis the script or voice bible calls for are craft, not accident. Cut accidental repetition, keep rhetorical repetition.
2. Off-goal or pacing drag. Stretches that do not serve the promised payoff: tangents, over-explanation, throat-clearing paragraphs. The test is "does this earn its runtime for this video's goal?", judged against `brief.md`.
3. Contradiction or confusion. Statements that conflict, a claim later walked back, an ambiguous antecedent, a muddied argument. Open loops belong here: a promise the video sets up and never pays off is a structural defect, and it has two clean fixes, cut the setup or re-record the payoff.
4. Errors and misstatements. Factually wrong or misspoken content. Two outcomes: cuttable (remove it and the piece still stands) or load-bearing (the point matters but is wrong), which is a re-record.

## The rule that outranks all of the above

Never apply a finding from a transcript-read timecode. Re-detect the span against the audio first.

The pass produces good findings and bad coordinates: source-timecode estimates read off a transcript drift to the wrong windows, so a blind apply cuts the wrong spans. Re-detecting each span by pattern against the kept audio before touching the EDL is what catches it.

So:

- Quote findings by CLEAN time for the human (that is what the preview shows), and apply them by SOURCE time against the EDL. `edited_transcript.py` emits both for every word so neither is ever derived by hand.
- Before applying any span, re-locate it in `cut/edited-words.json` by its words, then snap the resulting cut edges into audio silences from `cut/audio-map.json`, exactly as the mechanical tier does. A cut edge that cannot reach a silence needs an ear before it is applied.
- Word-level findings are lower confidence than idea-level ones and must be marked. You are reading a transcript, not hearing audio: a doubled word in the text may be a transcription artifact rather than a real stumble, and acting on one triggers a pointless re-record. Idea-level findings survive transcription noise; word-level findings do not.

## Reuse the reviewers that already ship

BMad already has the engines this needs. Adapt them, constrain them to subtract-only, and map their findings onto the five operations. Invoke them as skills; never read into another skill's folder.

- `bmad-editorial-review-structure` proposes cuts, reorganization, and simplification while preserving comprehension. The core engine for redundancy, drag, and ordering.
- `bmad-review-adversarial-general` and `bmad-review-edge-case-hunter` for contradiction, confusion, and error hunting.
- `bmad-editorial-review-prose` for sentence-level clarity, which here means "does the seam read", not "is this the best phrasing".

## Output

`cut/editorial-review.md`, from the template in `{skill-root}/assets/editorial-review-template.md`. A recommendation list for the human at the gate. Nothing is auto-applied, ever.

Every item carries: the span (clean and source timecodes plus the quote), the type, a severity, the reasoning, the proposed operation, a seam check for anything cuttable, and an explicit confidence marker on word-level findings.

Fold the itemized calls into `cut/cutplan.md` so gate 2 presents one list: the mechanical judgment calls and the content calls together, with routine trims grouped into a line and everything the creator might disagree with itemized.

## Two extensions, on request only

Both still honor "select spoken spans, never fabricate words". Neither is part of the default pass; offer them, do not run them.

- Resequencing. Because the pass understands the argument, it can propose moving a self-contained segment for better flow. Risk scales with format: low on loose long-form and livestream VODs where segments are modular, high on a tight talking-head where continuity, jump cuts, and eyeline all break. Offer freely on `livestream-vod`, propose cautiously on `talking-head`, never auto-apply.
- Highlight and sizzle mining. The same content ranking that finds redundancy finds the best moments: hot takes, quotable lines, energy peaks. It can assemble a cold-open sizzle or a highlights reel, which is a large win on a 1.5 hour VOD, and it is still subtractive. Natural consumers are the video's own cold open, mc-package, and short-form derivatives.

## Checklist

- The pass read `cut/edited-transcript.md`, not `script.md` and not the raw transcript.
- Every finding carries both clean and source timecodes, taken from the emitted transcript rather than converted by hand.
- Every word-level finding is marked as needing audio confirmation; idea-level findings are not.
- Every proposed cut has a seam check quoting the join it would create.
- Deliberate repetition (callbacks, rule of three, the script's own emphasis) was checked before anything was called redundant.
- Re-record flags are collected into a pickup list the creator can shoot from.
- Hand-to-beats items are listed separately, ready to seed the beat table.
- Nothing was applied. The document is a recommendation list, and the creator's calls at gate 2 decide what happens.
- When calls are applied, each span was re-detected against the audio and its edges snapped into silences before the EDL was touched.
