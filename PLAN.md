# Epic: skills that drive a model, not documents that address a reader

Branch `fix-cut-pipeline`, written 2026-07-26. Each story is executed sequentially
by an agent that may hold nothing but this file, so every story carries its own
context: the numbers are measured, the audits are regenerable with the commands
given, and the standards are stated here rather than assumed.

## Ground rules for every story

Read these before starting any story. They are the working standard; a story
that violates them is wrong even if its AC pass.

**Where you are.** The repo is
`/Users/brianmadison/bmad-code/bmad-os-repos/bmad-manticore/fix-cut-pipeline`.
Read `AGENTS.md` at the repo root first: module conventions, design invariants,
doc style (no em-dashes, blank line after every heading, no bold in list items,
ISO dates). Then read the quality canon, which is the bar all prose is held to:

- `/Users/brianmadison/bmad-code/bmad-os-repos/bmad-manticore/.claude/skills/bmad-workflow-builder/references/prompt-quality-canon.md`
- `/Users/brianmadison/bmad-code/bmad-os-repos/bmad-manticore/.claude/skills/bmad-workflow-builder/references/skill-quality-principles.md`

**Scope rule: every file in a skill is guidance for the model in use.** Not
just SKILL.md. Everything a skill progressively discloses, references, asset
prose, templates, engine docs, is loaded by a model mid-task and is held to the
same bar: destination-first shape, the earn-its-place test, no human-reader
apparatus. There is no such thing as a "reference for the human" inside a
skill folder.

**The defect being removed.** Overspecification is pinning down detail the
outcome does not require: telling the model how when it only needs what,
removing judgment a capable model would have exercised correctly. The test is
whether a capable model would do this correctly without being told; if yes, the
words are friction even when accurate, even when they appear only once.
Repetition is not the test, constraint is. Over-explanation is justifying a
point past the moment it lands: a reason given for an instruction that already
stands on its own.

**What must survive, without exception.** Losing any of these is a failure,
not a trade:

1. Every script invocation verbatim: the `uv run` command lines, flags,
   argument order, output paths.
2. Every artifact path, config key, and template variable.
3. Every number: thresholds, quotas, floors, durations, percentages, exit
   codes. (Story 6 deletes four quota literals deliberately; that is the only
   sanctioned exception in this epic.)
4. Every gate stop: which gate, that it is a hard stop, that only the
   creator's explicit approval moves it.
5. Gotchas whose trigger the model cannot recognize. A rule preventing a
   mistake the model would not know it was making stays inline in SKILL.md,
   never in a reference, because the model cannot load a file for a situation
   it does not know it is in. When in doubt, keep it.
6. The why behind any non-obvious rule. Cut the third telling of a why, never
   the only one.

**Budgets.** SKILL.md wants 2000 tokens, 3000 is the hard ceiling. Over the
ceiling means progressive disclosure, never prose compression. References run
to about 4500 for multi-branch, 9000 for single-purpose.

**Commit discipline.** One commit per story, message describing the story. No
AI attribution footers. Never push to the remote.

## Execution order

Stories run in this order: **1, 2, 3, 4, 7, 5, 6, 8.**

- Story 1 writes the invariants that stories 2, 3, 6, 7 cite.
- Story 7 runs immediately after Story 4 because both rewrite the same
  `## On Activation` blocks; back to back means each skill's block is touched
  in two adjacent commits instead of two distant ones.
- Story 5's AC and Story 6's central rationale both require Story 7 to have
  landed: 5 routes a missing checklist through the Story 7 pattern, and 6
  deletes fallback quotas that are only safe to delete once absence is loud.

## Verification toolbox

The commands behind every AC that says "green" or "clean". Run from the repo
root.

```bash
# all 31 skill test suites (CI-equivalent)
for t in $(find skills -path "*/tests/test-*.py" | sort); do
  echo "=== $t"; uv run "$t" || exit 1
done

# genericity release gate (CI-equivalent)
uv run skills/mc-setup/scripts/lint_genericity.py skills/ docs/ README.md CHANGELOG.md

# token counts and structure validation (builder tooling; --help for usage)
uv run /Users/brianmadison/bmad-code/bmad-os-repos/bmad-manticore/.claude/skills/bmad-workflow-builder/scripts/count_tokens.py <files>
uv run /Users/brianmadison/bmad-code/bmad-os-repos/bmad-manticore/.claude/skills/bmad-workflow-builder/scripts/quick_validate.py skills/<name>
```

Known-red baseline: CI currently fails on 5 pre-existing genericity findings in
`skills/mc-cut/references/editorial-pass.md` (real sibling skill names). They
predate this epic; the AC everywhere is "no NEW findings", not "zero findings".

## The thesis

Four separate complaints turned out to be one. `AGENTS.md` says taste lives in
files, meaning the creator's files, and mechanics live in scripts. In practice
the module keeps its own taste, addresses human readers, and resolves paths by a
rule that is false 126 times. Each story below removes one way the module speaks
for the creator or to the wrong audience.

Measured baseline, all `.md` outside `scripts/` and `tests/`, whole skill
folder per cell. Where a story quotes a smaller number for a skill it means
SKILL.md alone (mc-agent's SKILL.md is 2483 of its 5424).

| Skill | tokens | Skill | tokens |
|---|---|---|---|
| mc-setup | 13039 | mc-package | 6178 |
| mc-graphics | 8164 | mc-agent | 5424 |
| mc-cut | 7983 | mc-pipeline | 4127 |
| mc-beats | 7781 | mc-audio | 2197 |
| mc-assets | 1847 | mc-retro | 1512 |
| mc-script | 1452 | mc-new | 913 |
| mc-stream-pack | 795 | mc-braindump | 732 |
| mc-outline | 708 | | |

---

## Story 1: the three invariants

**As** a maintainer, **I want** the rules written down once at module level **so
that** every later story cites them instead of reinventing them, and the next
skill someone adds inherits them.

Add to `AGENTS.md` design invariants, in these words or better:

1. **Absence is never silent.** A skill loads the creator files it needs on
   activation. If one is missing it names the file, says what it cannot do
   without it, routes to mc-setup, and stops. The only permitted alternative is
   a fallback the skill states out loud at the moment it bites. No fallback may
   change creative output without saying so.
2. **Bare paths are the current video project.** A bare path in skill prose
   resolves against the current video project (`{video-path}`). Files inside
   the skill's own folder always carry `{skill-root}`. `{project-root}` keeps
   its existing meaning, the repo working directory.
3. **Every file in a skill addresses the model executing it, never a human
   reader.** This covers everything the skill progressively discloses,
   references, asset prose, templates, engine docs, not only SKILL.md. No
   citation blocks, no source URLs, no provenance or dated research claims.
   A URL a skill may legitimately name is one it installs from or runs, never
   one it cites. Provenance a maintainer wants to keep goes in the commit
   message or `TODO.md`.

**AC**

- Three invariants present in `AGENTS.md`, each stating rule plus exception,
  none referring to this plan.
- Invariant 3 explicitly covers all files a skill ships, not only SKILL.md.
- Each of stories 2, 3, 6, 7 cites its invariant rather than restating the rule.

---

## Story 2: `{video-path}` and the bare-path inversion

**As** a model executing a skill, **I want** one unambiguous meaning for a bare
path **so that** I do not look for `beats/STORYBOARD.md` inside the skill folder.
Cites invariant 2, which fixes the meaning of a bare path, `{skill-root}` and
`{project-root}` module-wide.

Today every Resolution rules block says *"Bare paths and `{skill-root}` resolve
from this skill's installed directory."* That is false for the majority case:

| Kind | Occurrences |
|---|---|
| Bare **video-project** paths (`beats/beats.md`, `cut/edl.json`, `project.json`, `raw/`) | **126** |
| Bare **skill-relative** paths (`references/…`, `engines/…`) | 41 |
| Already explicit `{skill-root}/…` | 54 |

`assets/` is the sharpest case: it is a skill folder in mc-cut, mc-script and
mc-setup, **and** the video-project folder mc-assets writes `manifest.json` into.
Same token, two meanings, same module.

**Decision: invert the default rather than prefix 126 sites.** Carry invariant 2
into every Resolution rules block, and define `{video-path}` there for explicit
use where a line would otherwise be ambiguous. This is 41 edits instead of 126,
and it reduces tokens rather than adding them.

Naming note: `{video-path}` over `{project-path}` deliberately, because
`{project-root}` already means the repo working directory and the near-collision
is exactly the confusion being fixed. `{projects-path}` holds one folder per
video, so `{video-path}` = `{projects-path}/<slug>/`.

Audit commands, to regenerate the site lists rather than trust the counts:

```bash
# bare skill-relative paths that must gain {skill-root} (the 41)
grep -rEn '`(references|engines|scripts|assets)/[^`]*`' skills --include="*.md" | grep -v '{skill-root}'

# already-explicit sites, for the before/after check (the 54)
grep -rn '{skill-root}/' skills --include="*.md"
```

Every `assets/` hit needs reading, not pattern-matching: decide per site
whether it means the skill folder (gains `{skill-root}`) or the video project
(stays bare).

**AC**

- Resolution rules in all 15 skills read: bare paths resolve from the current
  video project; `{skill-root}` for skill files; `{video-path}` available
  explicitly; `{project-root}` unchanged.
- All 41 bare skill-relative paths carry `{skill-root}`.
- Zero bare paths remain that are ambiguous between the two meanings.
- A grep for `` `assets/ `` resolves unambiguously in every occurrence.

---

## Story 3: strip the human-reader apparatus

**As** a model, **I want** no citations or URLs in the files I execute **so
that** I do not go researching and loading web artifacts mid-task. Cites
invariant 3, which makes the scope explicit: references and asset prose are as
much the model's instructions as SKILL.md is.

| Target | Location | Weight |
|---|---|---|
| `## Sources` blocks | `mc-beats/references/cta-placement.md:113`, `mc-package/references/cta-placement.md:113`, `mc-beats/references/density-and-creativity.md:101` | 289 + 289 + 317 |
| 23 URLs | the same three files | inside the above |
| "Research-backed rules (2024-2026 era)" | both cta-placement copies | date-stamps itself, invites a staleness check |

Three URLs elsewhere are legitimate and stay: the uv installer in
`mc-setup/references/stack-windows.md`, the HyperFrames repo in
`mc-graphics/engines/hyperframes.md`, the skill-creation link in
`mc-agent/references/growing-the-studio.md`. Each is something to install,
run, or follow as a live instruction.

Audit commands:

```bash
grep -rn '^## Sources\|^## References\|^## Further' skills/
grep -rEn 'https?://' skills --include="*.md"
```

This story also covers the wider over-explanation sweep, using the definitions
in Ground rules. Justification and parenthetical density per 1k tokens, as a
triage hint only, not a finding: mc-graphics 16, mc-pipeline 16, mc-audio 13,
mc-script 13, mc-agent 11, mc-package 10, mc-new 10. **mc-graphics is the worst
by volume**, with 129 parentheticals across 8164 tokens. Real identification
needs reading, not the metric, and everything in "What must survive" survives.

One deslop agent already applied this correctly, deleting "Derived from studying
high-retention scripted educational YouTube" from `craft-checklist.md`. This
makes that judgment consistent.

**AC**

- Zero `## Sources` / `## References` / `## Further reading` headings under `skills/`.
- Zero citation URLs; the three functional URLs remain and are each named as an
  install or run target.
- No dated research or provenance claim survives in any skill file.
- Each of the seven highest-density skills gets a read-through pass, not a grep pass.
- `cta-placement.md` byte-identical across mc-beats and mc-package afterwards.

---

## Story 4: jettison `customize.toml` entirely

**As** a creator, **I want** one place per kind of preference **so that** setup,
retro, and my own edits are the only homes, and no skill carries a private
override surface.

Maintainer decision 2026-07-26: the concept goes from this project completely.
All 15 packaged files, and the `_bmad/custom/<skill>.toml` /
`<skill>.user.toml` override layer with them. The studio config
(`[modules.manticore]` in `_bmad/custom/config.toml`, plus `config.user.toml`
for personal overrides) is untouched and becomes the only config surface.

Audited contents and where each goes:

| Skill | Substantive keys | New home |
|---|---|---|
| **mc-assets, mc-audio, mc-beats, mc-braindump, mc-graphics, mc-new, mc-outline, mc-pipeline, mc-stream-pack** | **none: empty `[workflow]` boilerplate** | delete outright |
| mc-cut | `silence_floor_db`, `cutplan_flags`, `preview_flags`, `final_flags` | `[cut]` sub-table of the studio config |
| mc-package | `candidates` | `[packaging]` sub-table (mc-package's SKILL.md already uses that name) |
| mc-retro | `preserve` | `[retro]` sub-table |
| mc-script | `craft_checklist` | Story 5, installed template, indirection dies |
| mc-setup | 57 lines, the `[defaults]` studio config seed | `assets/studio-defaults.toml` |
| mc-agent | 42 lines, the `[agent]` persona and menu | inline in `SKILL.md` |

The three new sub-tables join the `[defaults]` seed in
`assets/studio-defaults.toml`, so mc-setup writes them and a fresh studio has
them.

### The ceremony is most of it

42 of the 50 resolved references in the module are the same three empty arrays:

| Reference | Count | Value everywhere |
|---|---|---|
| `{workflow.persistent_facts}` | 14 | `[]` |
| `{workflow.activation_steps_prepend}` | 14 | `[]` |
| `{workflow.activation_steps_append}` | 14 | `[]` |
| real value references | 8 | |
| `{agent.*}` | 7 | |

Every SKILL.md also carries a `resolve_customization.py` activation line for
this. 17 files reference the script.

### The two files that carry something real

**mc-setup's `[defaults]`** is not a customization surface, it is a seed
template, which is exactly what `assets/` already holds (`tokens.template.json`,
`blacklist-starter.md`, the format profiles). It moves to
`assets/studio-defaults.toml` unchanged in content.

**mc-agent's `[agent]`** becomes prose and a table in SKILL.md. Persona is about
200 tokens, the 7-item menu about 400; the ~500 remaining tokens are comments
explaining the customization mechanism and die with it. mc-agent's SKILL.md
grows accordingly; if it crosses the 3000 ceiling, its own over-explanation is
the first thing to cut (Story 3 measured 53 parentheticals in the skill).

This also retires the precedence rule added earlier in the branch, *"`[agent]`
wins over any description of Manny written here or anywhere else"*, which
existed to resolve a two-homes ambiguity. One home, no rule needed.

### The mc-retro decision

`mc-retro/SKILL.md:29` is not a sweep item, it is the one design decision in
this story. Retro's mechanism for durable per-skill corrections is today
"write a `workflow` key into `_bmad/custom/<skill>.toml`", the layer being
jettisoned. It rewrites to a split that matches the rest of the epic:

- Mechanical values (flags, thresholds) go to the studio config sub-tables
  above, edited surgically.
- Taste goes to the production bible (global) or the format profile's
  Learnings section (per-format), which is already the mechanism's documented
  fallback.
- No per-skill toml surface remains, and editing another skill's installed
  SKILL.md stays the documented last resort.

### Sweep list

Every site outside the toml files themselves, from
`grep -rn "customize\|resolve_customization\|_bmad/custom/mc-" skills/ docs/ AGENTS.md README.md`
(re-run it; do not trust this list over the grep):

- `AGENTS.md:15, 19` (module layout table), `:26` (the whole per-skill-trio
  convention sentence), `:17` (mc-setup row, `[defaults]` now in `assets/`)
- `README.md:124` (also still says "16 skills"; it is 15 since mc-ograf)
- `skills/module.yaml:10` comment
- `docs/user-guide.md`
- `skills/mc-cut/scripts/cutplan.py:169, 770` (code comments)
- All 14 SKILL.md activation lines invoking `resolve_customization.py`
- `mc-setup/SKILL.md:22` (BMad-init path check includes the resolver), `:58`
  and `:113` and `:124` (`[defaults]`/lane-status references repoint to
  `assets/studio-defaults.toml`), `:64` (marker cues repoint to
  `[cut] cutplan_flags` in the studio config)
- `mc-setup/references/bootstrap.md:41`
- `mc-setup/references/migration-0x.md:40` (repoint to `[cut] cutplan_flags`)
- `mc-agent/SKILL.md:17, 68, 70` (the resolver invocation and the manual
  three-file merge fallback both die when `[agent]` goes inline)
- `mc-agent/references/growing-the-studio.md:9` (tells creators new skills
  ship a `customize.toml`; they no longer do)
- `mc-pipeline/PIPELINE.md:9` (`[defaults.*]` naming note) and `:71` (the
  module-wide activation contract names the resolver)
- `mc-retro/SKILL.md:29` (the decision above)

### The risk, resolved: one platform reader exists, regression accepted

Verified 2026-07-26 against the platform source. The BMM installer's
`isAgentSkill()` (`tools/installer/ide/_config-driven.js:76-89`) classifies a
skill as an agent by testing `<skill-dir>/customize.toml` for a `[agent]`
block, driven by the GitHub Copilot platform's `commands_filter: agents-only`.
It fails silently when the file is missing, and it does not read SKILL.md or
`module.yaml`.

Maintainer decision 2026-07-26: full jettison anyway. mc-agent's file goes
with the rest, and mc-agent will not be classified as an agent by Copilot's
agents-only filter until the installer learns another detection path. Record
the regression and the platform fix (teach `isAgentSkill()` to read
`module.yaml` or SKILL.md frontmatter, a bmad-bmm change) in `TODO.md`.

Secondary, same decision: the `bmad-customize` core skill lists skills by
`customize.toml` presence, so all 15 mc-* skills disappear from its listing.
Correct, not a regression: there is no customization surface to list.

**AC**

- Zero `customize.toml` files under `skills/`.
- Zero `resolve_customization.py` invocations in any skill file, and zero
  references to `_bmad/custom/<skill>.toml` or `<skill>.user.toml` anywhere
  (the studio config files `config.toml` / `config.user.toml` remain).
- Zero `{workflow.*}` and `{agent.*}` references; the real values live in the
  `[cut]`, `[packaging]`, `[retro]` sub-tables or an installed template.
- `assets/studio-defaults.toml` seeds mc-setup exactly as `[defaults]` did,
  including the three new sub-tables, and the interview produces an equivalent
  `[modules.manticore]` for a fresh studio.
- mc-agent's persona and menu render from SKILL.md.
- `TODO.md` records the accepted Copilot agents-only regression and the
  bmad-bmm installer fix that lifts it.
- mc-retro records mechanical corrections in the studio config and taste in
  the bible or format-profile Learnings; no dangling reference to the old layer.
- The sweep grep above returns nothing but the studio-config sites that stay.
- 31 test suites green, no new genericity findings.

---

## Story 7: absence is never silent

Runs immediately after Story 4: both rewrite `## On Activation`, so touching
them back to back keeps each skill's block coherent. Cites invariant 1.

**As** a creator, **I want** to be told when a file I never built is changing my
output **so that** the module never quietly substitutes its taste for mine.

Audited: all 8 stage skills route to mc-setup for exactly one condition, an empty
studio config. **Zero** route for a missing taste file. Four mark them explicitly
optional (`when it exists`, `if it has been built`).

Dependency map, from grep of each SKILL.md:

| Skill | bible | voice | tokens | blacklist | exemplars | headshots |
|---|---|---|---|---|---|---|
| mc-outline | | yes | | yes | | |
| mc-script | | yes | | yes | yes | |
| mc-cut | yes | yes | | | | |
| mc-beats | yes | | yes | | | |
| mc-assets | yes | | | | | yes |
| mc-graphics | yes | | yes | | | |
| mc-package | yes | | yes | yes | | yes |
| mc-stream-pack | yes | | yes | | | |
| mc-retro | yes | yes | | yes | | |

Each skill gains one clause per required file in `## On Activation`, this
pattern verbatim with the two blanks filled:

> Read `<file>`. If it does not exist, tell the creator it is missing and that
> `<capability>` cannot happen without it, then route to mc-setup and stop.

Two existing fallbacks pass the invariant and stay: mc-cut's cadence fallback
(*"a deliberately tiny built-in soft-filler list, which is safe but generic"*)
and headshots blocking thumbnails. Both are already disclosed.

**AC**

- Nine skills load their row's files on activation using the pattern verbatim.
- A missing file produces: the filename, the capability lost, a route to
  mc-setup, and a stop.
- Zero occurrences of `when it exists` / `if it has been built` for a taste file.
- The two disclosed fallbacks survive verbatim.

---

## Story 5: creator templates installed at setup

**As** a creator, **I want** the files that shape my output to live in my brand
folder **so that** I can edit them and the skill obeys my version.

`mc-script/assets/craft-checklist.md` (531 tokens) is module content the skill
executes against. It becomes a setup-installed template in `{brand-path}`,
creator-editable, and mc-script always reads the project copy. Same pattern as
`tokens.json`, `blacklist.md`, and the format profiles already use.

Audit the other skill assets for the same treatment:

| Asset | Tokens | Assessment |
|---|---|---|
| `mc-script/assets/craft-checklist.md` | 531 | **Move.** Creator-editable retention rules |
| `mc-cut/assets/editorial-review-template.md` | 1328 | Evaluate. Output template, arguably creator-editable |
| `mc-setup/assets/*` | 6975 | Already the install-source pattern. Stays |

Install semantics matter and are easy to get backwards: creator-editable files
are **never** overwritten on re-run (the format-profile rule), module-owned
shared content **is** refreshed. Record which is which.

**AC**

- `craft-checklist.md` installs to `{brand-path}` at setup, is never clobbered
  on re-run, and mc-script reads the project copy directly.
- A missing craft checklist triggers the Story 7 pattern (landed by execution
  order), not a silent fallback.
- The editorial-review template decision is made and recorded either way.

---

## Story 6: the Production Bible owns style

Cites invariant 1. Story 7 has landed by this point, so a missing bible is
already loud; that is what makes the deletions below safe.

**As** a creator, **I want** my style defined once at setup and ratcheted by
retro **so that** the module stops holding opinions I cannot change.

mc-beats hardcodes four aesthetic judgments with no creator control:

| Hardcoded | Where |
|---|---|
| at least 6 distinct beat types over 5 minutes, no type over 40% of rows | `mc-beats/SKILL.md:42`, `references/density-and-creativity.md:11` |
| static cards under a third, 25% target, never consecutive | `SKILL.md:43`, `density-and-creativity.md:12` |
| beats-per-minute floors 3 / 1.5 / 0.7 | `SKILL.md:44`, the tier table `density-and-creativity.md:24-27` |
| "a plan below the floor is a failed plan" framing | `density-and-creativity.md` |

The creator's only lever is `graphics-frequency`, one of three tiers.
`production-bible-spec.md` section 5 makes it circular: it claims the bible owns
"the variety quota" then points at `density-and-creativity.md` shipped with
mc-beats, which states it as law with no override.

**These numbers are deleted, not relocated.** They exist only because nothing
required the bible; Story 7 now guarantees its absence is loud. Putting them in
a config default would create a second home for style and a permanent
precedence argument.

Work:

1. `production-bible-spec.md` section 5 specifies the quotas as creator-owned,
   with the global and per-project-type split the file already provides.
2. mc-setup interviews for them in the video-style pass, so a new studio leaves
   with real numbers. Shipped values appear as suggestions inside the interview,
   never as config defaults.
3. mc-beats reads resolved values from the bible. The four literals and the
   failed-plan framing come out of `SKILL.md` and the reference.
4. `density-and-creativity.md` keeps the taxonomy and trigger heuristics, which
   are craft, and stops stating quotas as law.
5. mc-retro can then ratchet them, which today it cannot.

**On motion recipes, the concern is largely not borne out.** `motion-recipes.md`
is framed as a library, not law: *"prefer these before invoking an engine
workspace"*, with only 4 binding-language hits in 2137 tokens. It is mechanics,
and mechanics belong in the module. The real gap is smaller: mc-graphics reads
both the bible and the recipes and never states which wins. Fix is one sentence
giving the bible's motion-feel section authority, plus routing learned motion
patterns to the bible via mc-retro.

**AC**

- Zero style quotas stated as literals in any mc-beats file.
- `production-bible-spec.md` section 5 self-contained, delegating to no skill.
- mc-setup interview produces the values; a fresh studio has them.
- mc-retro can edit them, demonstrated by naming the file and section it edits.
- mc-graphics states bible-over-recipes precedence in one sentence.
- F4 (scripting the quotas) remains out of scope until this lands, then
  becomes safe against resolved values.

---

## Story 8: verification and re-sync

**As** a maintainer, **I want** the epic's claims re-proven at the end **so
that** nothing regressed between stories. Run everything in the Verification
toolbox, then check:

**AC**

- 31 test suites green; `quick_validate` clean on 15; no new genericity
  findings beyond the 5 pre-existing in `editorial-pass.md`.
- No SKILL.md over 3000 tokens (count with `count_tokens.py`).
- `cta-placement.md` byte-identical across mc-beats and mc-package.
- Zero script invocations, CLI flags, config keys, or numeric thresholds lost
  against the branch point, excepting the four quota literals Story 6
  deliberately removes.
- Every gate and its creator-approval rule intact.
- No dangling internal links, no reference to a file or section a story
  renamed or removed.
- Re-measure the baseline table and record the final numbers in the closing
  commit message.

---

## Expected reduction

Estimates in this session have run optimistic three times, so these are
directions, not commitments.

| Story | Tokens |
|---|---|
| 2 path inversion | −150 to −300 |
| 3 sources, URLs, over-explanation | −1500 to −2500 |
| 4 customize.toml jettison | **−2200 to −2800** (15 files, 17 activation lines, 42 ceremony refs; mc-setup and mc-agent content relocates rather than dies) |
| 5 template move | ~0, relocation |
| 6 bible owns style | −350 to −500 |
| 7 activation clauses | **+350 to +550** |
| **Net** | **−3800 to −5500** of ~62,000 |

Reduction is a side effect. The point is that style becomes ownable, absence
becomes loud, paths stop lying, and the files stop talking to a reader who is
not there.

## Deliberately out of scope

- Shared-resources / `_bmad/{module}` architecture, the six cross-skill file
  citations, and PIPELINE.md's location. Deferred by the maintainer 2026-07-26 as
  a future platform improvement.
- **F4**, scripting the beat-table quotas. Safe only after Story 6.
- CI is red on 5 pre-existing genericity findings in
  `mc-cut/references/editorial-pass.md`, from citing real sibling skill names.
  Four allowlist entries in `lint_genericity.py` fixes it. Unrelated to this
  epic and still needs a maintainer decision.
