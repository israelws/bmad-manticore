# Review rules

Checked by code review agents on every change; there is no lint for these. Judgment beats keyword matching: the question is always whether the rule is broken, not whether a word appears.

1. Nothing user-, brand-, or show-specific ships: no personal names, real project slugs, brand colors, or machine-specific paths in module content. Naming a BMad skill or module that a file actually invokes is fine.
2. No secrets anywhere, ever: env var names only, and key sourcing is mentioned only inside the opt-in branch that uses it.
3. No paid or metered vendor in any default; vendors exist only as explicit opt-in choices.
4. A URL must be something the model installs from, fetches, or runs. No citation, source, or reading-list URLs.
5. No provenance or dated research claims in anything a skill ships, asset prose and templates included.
6. Config keys are kebab-case.
7. Every check the pipeline claims to perform is a script that exits non-zero; "inspect X" prose is only acceptable beside a script that fails when X is wrong.
8. Gates are sacred: no change may let a stage proceed past a gate without the creator's recorded approval.
9. Scripts run only via `uv run`, carry PEP 723 metadata, take explicit arguments, and do no config discovery of their own.
