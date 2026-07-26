# The series template contract

One file per series at `{brand-path}/templates/<series>.md`, filename matching the `series` value
in `project.json`. mc-setup's brand scaffold creates the `templates/` folder and one file per
recurring series the creator names; mc-package is the consumer.

Load this when `series` in `project.json` is set. Its locked anchors bind every title and
thumbnail candidate produced for the episode.

## The shape both sides honor

- Locked anchors: everything each episode repeats so the series reads as a set in a feed.
  Thumbnail layout constants (face position and scale, wordmark or episode badge placement,
  background treatment, palette accents drawn from `tokens.json`) and the title pattern (fixed
  prefix, suffix, or numbering scheme).
- Per-episode variables: the slots each episode fills. Hook words, episode-specific imagery, guest
  name, episode number.

Locked anchors are non-negotiable within an episode. Changing them is a series-level decision that
routes through mc-retro into the template, ISO dated, so packaging wins compound across the
series.

## When the file is missing

When `series` is set but the template file does not exist, flag it, draft one from the Production
Bible's series notes plus this episode's choices, save it to `{brand-path}/templates/`, and tell
the creator the next episode inherits it.
