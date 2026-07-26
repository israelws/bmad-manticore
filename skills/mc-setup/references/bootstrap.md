# Bootstrapping BMad core

Load this when any of the four paths checked on activation is missing, which means
the project is not BMad-initialized. Manticore installs nothing itself: it runs the
bmad-method installer and then verifies the result.

Say the project is not initialized and confirm before running anything. The installer
writes `{project-root}/_bmad/` plus IDE integration files for the chosen tool, so this
is a system change the creator agrees to first.

## Resolve the tool id

`claude-code` under Claude Code. Otherwise run `npx -y bmad-method install --list-tools`
and let the creator pick.

## Install

No `{project-root}/_bmad/` at all:

```
npx -y bmad-method@latest install --directory {project-root} --modules core --tools <tool-id> -y
```

Never omit either flag. A bare `-y` installs the default module set rather than just
core, and fresh `-y` installs fail without `--tools`.

`{project-root}/_bmad/` exists but is incomplete:

```
npx -y bmad-method@latest install --directory {project-root} -y
```

That quick-update re-syncs `{project-root}/_bmad/scripts/` and keeps configured tools.
If it fails, retry with `--action update --modules core --tools <tool-id>` added.

## Verify before continuing

- Both resolver scripts exist under `{project-root}/_bmad/scripts/`.
- `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.manticore`
  exits 0. Empty output just means the interview has not run.
- `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root}`
  returns this skill's `[defaults]`.

If uv itself is missing, bootstrap uv first (see the dependencies section of SKILL.md),
then verify.

## When it will not install

On verification failure, stop and surface the installer output. Never hand-copy scripts
or vendor a resolver of your own; a project running against a copied resolver diverges
from every other BMad Method module in it.

If npx, node, or the network is unavailable, or the creator declines, have them run
`npx bmad-method install` interactively from the project root (core alone is enough for
Manticore), then re-run mc-setup.

A stale npx cache can serve an old CLI that lacks current flags. On unknown-option
errors, run `npm cache clean --force` and retry.
