# Generative Editing Rules

Hard rules for every generative asset lane, image or video, any provider. mc-assets applies them on every farm and every revision, and `farm_asset.py` restates them in its docstring. Violating them produces the classic generative failure modes: compounding artifacts, mutated subjects, and wasted iteration loops.

## Rule 1: never chain generative edits

Every revision regenerates from the ORIGINAL source assets with all accumulated fixes expressed in one prompt. A generated output is never the base for the next edit: a revision of a revision degrades like a photocopy of a photocopy. When a tweak is needed, send ALL the original assets again with one improved prompt, not the last version plus a delta. `--ref` takes real photography or the original source only, never a prior generation.

## Rule 2: composite small deterministic fixes, never regenerate them

A logo swap, one wrong text line, a color correction: these are programmatic composites (rsvg, ffmpeg). Regenerating a whole asset to fix one deterministic element risks everything else that was already right.

## Rule 3: self-inspect before the creator sees anything

Inspect every output against the request at zoom: the gesture points at the right target, the expression matches, no anatomical or rendering artifacts, all text is exactly the requested string. An output that fails inspection is retried, not shown.

## Rule 4: people come from their original photos

To put someone in an asset, pass their approved original photo as `--ref` and say so in the prompt: "use the person in this image to {whatever the asset needs}". Current models handle the likeness from there, with no masking or cutout step. What breaks likeness is chaining, so every revision re-sends that same original photo with the revised prompt.

## Rule 5: prompting

- Concrete subject, camera and framing, lighting, mood, and a brand-adjacent palette where it fits.
- Short text that must appear in the asset is quoted as an exact string ("the badge reads exactly: \"1.0\""). Current models render short quoted strings reliably and exactness comes from the quoting, so the old blanket warning that generated text is gibberish no longer holds.
- Wardrobe and object edits spell out the physics (how fabric hangs, what the object rests on, what occludes what) instead of naming the item alone.
- List what must NOT change, explicitly, every time: face, pose, lighting, background, framing.
- Ask for margins when content sits near canvas edges; generation crops and drifts at borders.
- Expression variants from one reference image use the pattern "use this person but have them {expression}".

## Rule 6: long jobs run in background, deadlines cap iteration

Enforced in the farming flow rather than here; the mc-assets SKILL.md carries it.
Numbered so the rule numbering stays aligned with `farm_asset.py`, which cites
these rules by number in its docstring and in its error text.
