# mc-setup carve plan (2026-07-26)

`skills/mc-setup/SKILL.md` is 6,060 tokens: 2.0x the 3,000 hard budget and 3.0x the
2,000 desired tier. The worst file in the module by a wide margin, and worse than
mc-cut was before F1 (4,930).

Measured with the builder's own `scripts/count_tokens.py`. Same canon as F1:
`references/prompt-quality-canon.md` and `references/skill-quality-principles.md`
in `bmad-workflow-builder`.

## What is actually wrong

### It is a route, not a destination

Fifteen numbered steps: 0, 1, 1a, 2, 2b, 3, 3b, 3c, 3d, 4, 4b, 5, 6, 7, 8.

There is no 2a, no 3a, no 4a. The letters are insertion scars: every time a step was
added, it got suffixed onto its neighbor rather than renumbering, because renumbering
would have meant fixing every cross-reference. There are 31 of those cross-references
inside the file ("the step 8 pending list", "the step 3c answers", "step 4b measures
it for real"), so the numbering is now load-bearing scaffolding that exists to hold up
more scaffolding.

`references/standard-fields.md`: a number implies a fixed order the model must march
through and fights the outcome-driven shape. Setup is the clearest case in the module,
because a re-run is explicitly a menu, not a march. The file says so in step 1 and then
spends 5,900 tokens laying out a march anyway.

### Section weights

| Tokens | Section | Disposition |
|---|---|---|
| 720 | 3. The basics interview | Question bank. Cut to non-inferables |
| 649 | 1a. 0.x migration | Recognizable trigger. Carve to a reference |
| 597 | 3c. The video style interview | Restates `assets/production-bible-spec.md` |
| 510 | 0. Bootstrap BMad core | Recognizable trigger. Carve to a reference |
| 463 | 4. Brand build | Keep, tighten |
| 387 | 5. CLI tools and asset lanes | Keep, tighten |
| 374 | 8. Write and confirm | Keep. This is the outcome |
| 330 | 3d. Audio lanes | Partly restates mc-audio's own reference |
| 282 | 3b. Render consent | Keep. Consent is non-inferable |
| 274 | 2. Dependencies | Keep, tighten |
| 273 | 4b. Guided voice-bible build | Restates `assets/voice-bible-spec.md` |
| 271 | 2b. HyperFrames graphics skills | Keep, tighten |
| 239 | 7. Keys and .env.example | Keep |
| 156 | Rules | Keep. These are the gotchas |
| 146 | 1. Locate and load | Becomes On Activation |
| 123 | 6. Editor integration | Keep |

### It restates two files that ship beside it

`assets/voice-bible-spec.md` has a section titled "How to build it": pull 5 to 10
transcripts with `yt-dlp --write-auto-subs`, save the best into `exemplars/` with
frontmatter, deconstruct with evidence quotes, cite a verbatim example per rule,
measure real wpm. Step 4b restates all of it in prose.

`assets/production-bible-spec.md` has a section titled "How mc-setup builds it",
covering the emulation-link distillation, the echo-back-and-confirm move, and the
answers-land-in-both-places rule. Step 3c restates all of it.

Both specs are read at build time regardless. The file says so itself: "If declined,
the spec stays in place as the build instructions." So these are not two tellings for
safety, they are one telling in the wrong place plus a copy that can drift.

### It restates customize.toml

`customize.toml` is 236 lines and owns `[defaults]`. SKILL.md says so in its second
paragraph, then inlines the values anyway: 145 wpm, all four `manticore/*` paths,
parakeet-tdt-0.6b-v3, onnx-asr, kokoro-local, musicgen-local, audioldm2-local, the
crf and loudness defaults. The canon cuts restated facts.

### Missing required structure

- No `## Resolution rules`, though the file uses `{skill-root}`, `{project-root}`,
  `{brand-path}`, `{formats-path}`, and `{engines-path}`. (Module-wide: 0 of 16 had
  one before F1; mc-cut is now 1 of 16.)
- No `## On Activation`. The activation work is buried inside "### 1. Locate and load".
- Description is 79 words with no quoted trigger, tied for longest in the module. It is
  a table of contents of the steps, not a routing signal. The required format is
  `[5-8 word summary]. [Use when user says "phrase" or "phrase".]`

## What must stay inline

The gotcha rule from `skill-quality-principles.md`: a rule whose trigger the model
cannot recognize never carves to a reference, because it cannot load a file for a
situation it does not know it is in. These qualify:

- Never touch `{project-root}/_bmad/config.toml`; Manticore's home is the `custom/` layer.
- Presence checks only for secrets. Never read, echo, or store values.
- Paid and metered vendors are opt-in only. No vendor name, dashboard, or pricing
  outside the branch where the creator chose that lane.
- Never claim a planned lane works.
- Idempotent, never clobber, a no-change re-run writes nothing.
- `ograf-editable = true` ONLY for DaVinci Resolve 21+.
- Headshots are approved photos only; never arbitrary frames from footage.
- Fill for real. A placeholder survives only when the creator has nothing to give, and
  every survivor goes on the pending list loudly.
- Consent for the render-first default is recorded, not assumed.

## Proposed shape

Destination paragraph, then named sections. Draft opening:

> Act as the studio's configurator. The outcome is a studio config every mc-* skill can
> resolve, a brand folder with real content in it rather than placeholders, and an honest
> report of what is still missing. Two consumers set the bar: every other mc-* skill reads
> `[modules.manticore]` and fails closed without it, and the creator needs to know what
> will actually happen on their first project before they start one.

Sections, no numbers: Resolution rules, On Activation, Dependencies and platform,
Interview the studio, Build the brand, Register the tools, Write and report, Rules.

## References to add

| File | From | Est. tokens |
|---|---|---|
| `references/bootstrap.md` | Step 0 | ~550 |
| `references/migration-0x.md` | Step 1a | ~700 |

Both have triggers the model can recognize from a state it checks anyway (the four
paths are missing; the config exists but lacks the 1.0 tables), so both are clean
progressive-disclosure carves rather than hidden gotchas.

No new reference for the interview. The two asset specs already are that reference.

Estimated result: 1,800 to 2,200 tokens, inside the desired tier.

## Cost outside mc-setup

Unlike mc-cut, this file's step numbers ARE cited externally. Renaming sections breaks
4 citations, all of which need updating in the same commit:

| File | Citation |
|---|---|
| `skills/mc-assets/SKILL.md` | "route to mc-setup step 5 if none exists" |
| `skills/mc-graphics/SKILL.md` | "mc-setup installs them (step 2b)" |
| `skills/mc-graphics/engines/hyperframes.md` | "Installed at setup (mc-setup step 2b)" |
| `skills/mc-setup/customize.toml` | "mc-setup step 5 fills the vendor's" |

Each becomes a reference by section name. `skills/mc-stream-pack/SKILL.md` also matches
a step-number grep but its "step 2" is mc-ograf's, not mc-setup's; it needs no change.

## Verification plan

Same as F1: invariant-term grep before and after, `quick_validate.py`,
`scan-path-standards.py`, `lint_genericity.py`, the mc-setup script tests, and a
disposition table mapping every old section to kept, moved, or deleted-with-citation.

No script changes. This is a documentation carve.

## Result (2026-07-26)

6,060 to 2,851 tokens, a 53% cut. 184 lines to 126.

| Check | Result |
|---|---|
| SKILL.md tokens | 2,851 (under the 3,000 hard budget, over the 2,000 desired tier) |
| `quick_validate.py` | `{"ok": true, "errors": []}` |
| `scan-path-standards.py` | 0 findings in every category |
| `lint_genericity.py` | Clean on all 3 new/rewritten files |
| mc-setup test suites | 3 of 3 pass (`check_deps`, `lint_genericity`, `merge_profile_frontmatter`) |
| Invariant survival | 34-term grep, all present |
| Description | 79 words to 36, now carrying 3 quoted triggers |
| Numbered steps | 15 to 0 |
| Internal step cross-references | 31 to 0 |

### Disposition of every old section

| Old | Tokens | Disposition |
|---|---|---|
| 0. Bootstrap BMad core | 510 | Moved to `references/bootstrap.md`. Trigger (four paths missing) stays inline as On Activation item 1 |
| 1. Locate and load | 146 | Became `## On Activation` plus the routing table |
| 1a. 0.x migration | 649 | Moved to `references/migration-0x.md`. Trigger (missing 1.0 tables) stays inline in the routing table |
| 2. Dependencies | 274 | Kept as `## Dependencies and platform` |
| 2b. HyperFrames skills | 271 | Kept, compressed. The why survives; "confirm first" cut as a restatement of Rules |
| 3. The basics interview | 720 | Question bank deleted. Four traps kept |
| 3b. Render consent | 282 | Kept. Consent is performed, so it cannot be inferred away |
| 3c. Video style interview | 597 | Deleted as a restatement of `assets/production-bible-spec.md`. Two moves the spec lacks kept |
| 3d. Audio lanes | 330 | Compressed to the three honesty gotchas; ladder cited to mc-audio |
| 4. Brand build | 463 | Kept as `## Build the brand`. Manifest collapsed to one sentence, four governing rules kept |
| 4b. Guided voice-bible build | 273 | Deleted as a restatement of `assets/voice-bible-spec.md`. The wpm write-back kept |
| 5. CLI tools and asset lanes | 387 | Kept as `## Register the creator's tools` |
| 6. Editor integration | 123 | Kept verbatim in substance |
| 7. Keys and .env.example | 239 | Kept, minus a restatement of Rules |
| 8. Write and confirm | 374 | Kept as `## Write and report` |
| Rules | 156 | Kept. 6 rules to 5; the dropped one was the idempotency rule, now in the opening |

### Deletions, with the surviving citation

| Deleted | Where it still lives |
|---|---|
| The question list for basics | `customize.toml` `[defaults]`, named as the authority |
| Default values (145 wpm, paths, lanes, crf, LUFS) | `customize.toml`, same |
| Voice-bible build procedure | `assets/voice-bible-spec.md` "How to build it" |
| Production-bible build procedure | `assets/production-bible-spec.md` "How mc-setup builds it" |
| Audio ladder detail | mc-audio `references/audio-lanes.md` |
| "Confirm first" on the HyperFrames install | Rules, first line |
| "Metered APIs never a silent default" (tools section) | Rules, third line |
| "(presence only)" at the key check | Rules, second line |

### External citations updated

| File | Now reads |
|---|---|
| `skills/mc-assets/SKILL.md` | "route to mc-setup's tool registration" |
| `skills/mc-graphics/SKILL.md` | "mc-setup installs them" |
| `skills/mc-graphics/engines/hyperframes.md` | "Installed at setup by mc-setup" |
| `skills/mc-setup/customize.toml` (x2) | "during setup"; "tool registration fills the vendor's" |

`skills/mc-stream-pack/SKILL.md` matched the grep but its "step 2" is mc-ograf's. Unchanged, correctly.

### Where I missed

The plan estimated 1,800 to 2,200 and the result is 2,851. The estimate was wrong, not
the file. After the two branch carves, every remaining section fires on a first run:
dependencies, HyperFrames, interview, brand, tools, editor, keys, report. Carving any of
them would have been size-driven, which the canon rejects ("carve by relevance, not
size"). mc-setup configures 12 config tables, 5 brand assets, a tool registry and an
installer, and that surface does not compress to 2,000 without pushing load-bearing
content out of reach.

### Found while verifying, not fixed

`skills/mc-cut/references/editorial-pass.md` ships 5 brand-term findings that
`lint_genericity.py` gates on in both `quality.yaml` and `release.yaml`. It arrived in
commit 0663d52, so CI is red on this branch independently of the F1 and mc-setup work.
The names it cites (`bmad-editorial-review-structure`, `bmad-review-adversarial-general`,
`bmad-review-edge-case-hunter`, `bmad-editorial-review-prose`) are real sibling skills of
exactly the class the allowlist already covers (`bmad-workflow-builder`, `bmad-bmm`,
`bmad-autopilot`). The fix is 4 allowlist entries in `lint_genericity.py`, but that is a
policy change about what may ship, so it is not folded into this carve.
