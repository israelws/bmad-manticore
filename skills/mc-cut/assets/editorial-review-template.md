# Editorial Review: the content pass

Template for `cut/editorial-review.md`. The spec is `{skill-root}/references/editorial-pass.md`; this is the shape of its output. Replace every angle-bracket placeholder and delete any section that has no findings rather than leaving it empty.

Written for the creator to read at gate 2 alongside `cut/cutplan.md`. Nothing in it has been applied.

---

# Editorial Review

Project: `<slug>`
Run on: the EDITED transcript (post mechanical cut), `<N>` words, `<M:SS>` runtime, reconstructed from `words.json` intersected with the kept segments of `cut/edl.json`.
Judged against: `brief.md` (the goal), `script.md` (the intent), and `{brand-path}/voice-bible.md`.
Date: `<YYYY-MM-DD>`

## How to read this

This is the subtractive pass. It can only recommend four things, and nothing is applied until you say so:

- CUT, remove a spoken span, with a seam check that it still flows.
- RE-RECORD, a pickup; the only way to fix or add load-bearing content.
- HAND TO BEATS, do not cut, solve it with a visual. Seeds the beat table.
- GENERATE, synthetic-voice fill. Consent-gated, tiny bridges only.

Read this caveat first. This pass read the transcript TEXT and cannot hear the audio. Idea-level findings (structure, redundancy, logic, ordering) are high confidence and survive transcription noise. Word-level findings are marked VERIFY AUDIO: the transcript shows a stumble, but it may be a transcription artifact rather than something you actually said. Check those against the audio before cutting. Anything high-stakes (a name, a URL, a number) is listed first.

Times are given as `clean / src`. Clean time is what the preview shows. Source time is what the EDL edits. Both come from `cut/edited-words.json`; neither was converted by hand.

## Verdict

`<One paragraph: is this polish or rescue? What is working? Say so plainly before listing problems, because a list of findings with no verdict reads as "this is broken" even when the piece is strong.>`

## Priority items

`<The three to five highest-leverage calls, each with the shape below. Order by leverage, not by timecode.>`

P1, `<one-line summary>`. [CUT | RE-RECORD | HAND TO BEATS | VERIFY AUDIO]
`<clean>` / src `<src>`, quoting: "`<the quote>`"
`<Why this matters, in two or three sentences.>`
Seam if cut: "`<...end of the preceding span>` → `<start of the following span...>`"
Recommendation: `<your call, and the tradeoff if the creator wants the other option>`

## Findings by category

### Redundancy

`<Points already made, restated with no new value. Conceptual, not verbatim. Note explicitly where you checked for and PRESERVED deliberate repetition (callbacks, rule of three, the script's own emphasis), so the creator can see the difference was considered.>`

### Off-goal and pacing

`<Stretches that do not earn their runtime against brief.md. Where a stretch could be either cut for pace or visualized for richness, offer both and say which you would pick.>`

### Contradiction and confusion

`<Conflicting statements, walked-back claims, ambiguous antecedents. Open loops belong here: a promise set up and never paid off, with its two clean fixes, cut the setup or re-record the payoff.>`

### Errors and misstatements

`<Factually wrong or misspoken content. Mark each cuttable (the piece stands without it) or load-bearing (the point matters but is wrong, so it is a re-record). Every word-level item here is VERIFY AUDIO.>`

### Leftover stumbles the mechanical pass missed

`<Doubled words, false starts, backups. All VERIFY AUDIO. Note which ones sit on cut seams: those may be artifacts of the mechanical cut rather than the delivery, and the fix is re-trimming the seam, not a re-record.>`

## Hand to beats

`<Not cuts. The moments best solved with a visual, ready to seed the beat table: the spoken span, what the visual would carry, and why the ear alone is struggling. This is the bridge between the content pass and the visual pass.>`

## Re-record pickup list

`<Only if there are re-record flags. A shot list the creator can read from: for each, the line to record, why, and where it splices. If there are none, say so.>`

## Your decision checklist

Verify against audio first:
- [ ] `<high-stakes word-level items>`

Content calls, your taste:
- [ ] `<each CUT or RE-RECORD call>`

Route to beats, no cut:
- [ ] Approve the hand-to-beats list to seed the beat table.

Nothing here has been applied. Tell me which items you want and I will apply the cuts (re-detecting each span against the audio and snapping its edges into silences before touching the EDL), assemble any pickup list, and carry the hand-to-beats items into the beats stage.

---

## APPLIED, `<YYYY-MM-DD>` (`<creator>`'s calls: `<summary>`)

`<Append this section only after the creator decides. It is the audit trail, and on the first real project it was the most useful part of the document.>`

Backup of the pre-editorial cut: `cut/edl.pre-editorial.json`. Runtime `<before>` → `<after>` (`<N>`s removed, `<X>` → `<Y>` segments). All cuts whole-word and silence-anchored.

Verification note: `<state explicitly what changed between the recommendation and the application. Transcript-read timecodes drift; if re-detecting against the audio moved any span, or revealed a finding was an artifact, say so here. This is the section that catches a blind apply.>`

Applied:
- `<each applied call, with its final source span>`

Deliberately NOT applied:
- `<each rejected call and the reason, including anything that turned out to be a transcription artifact or intentional rhetoric>`
