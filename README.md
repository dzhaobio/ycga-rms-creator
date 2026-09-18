# ycga-rms-creator

A Claude Code [skill](https://code.claude.com/docs) for writing, extending,
and reviewing `.rms` pipeline scripts for Yale YCGA's RMS ("Run My
Samples") SLURM job-orchestration DSL on McCleary.

This is an *authoring* skill, not a *runbook*: it doesn't run a fixed
sequence of operations for one recurring service (compare
`ycga-rnaseq-deg`/`ycga-rnaseq-deg-as`, which do). Instead it's a grammar
reference, a decision procedure for designing a new pipeline's steps,
dependencies, and resource/staging choices, a set of proven idioms to
reuse, and a linter to catch a known class of silent failure before
handing a draft back.

## Layout

- `SKILL.md` -- the workflow: how to go from a task description to a
  correct `.rms` script, plus the must-know engine quirks and how to
  validate a draft before finishing.
- `references/` -- the detail:
  - `grammar.md` -- the authoritative script grammar, read from the
    installed engine source (not just the docs, which have gaps and one
    directive that's flatly wrong for this build).
  - `manifest.md` -- sample sheet / manifest format.
  - `resources_and_staging.md` -- per-step `##ppn`/`##mem`/`##io`/`##local`
    decision tree, with value tables from real production scripts.
  - `idioms.md` -- reusable code snippets proven in production (PE/SE lane
    merge, genome-dispatch dict, cross-sample aggregation, etc.).
  - `engine_quirks.md` -- directives that are parsed but functionally dead
    on this engine build, silent-failure traps, and every place the
    official docs disagree with what the installed engine actually does.
  - `cli_and_environment.md` -- `rms` CLI flags, companion tools, live
    McCleary paths/queue names.
- `assets/` -- three short, clean, verbatim production scripts (two from
  James Knight, the RMS author; one from Dejian Zhao) as structural
  gold-reference examples.
- `scripts/validate_rms.py` -- a static linter that mirrors the real
  parser's structural rules and flags the specific silent-failure modes
  this engine build has (unresolved template variables, inert directives,
  forward `##after=` references, etc.). Not a substitute for a real
  `rms -t` compile check, but catches things that check never will.

## Status

Built 2026-09-18, from reading the installed RMS engine source directly,
the official docs at rms.readthedocs.io, and a survey of real production
scripts under `/home/dz288/rms/` and `/home/dz288/rms/rms_JamesKnight/`.
The full research -- file/line citations against the engine source,
verbatim doc excerpts, quantitative directive-frequency tables across the
production-script survey, and a reconciliation of every place the three
sources disagreed -- lives in the `ycga-rms-creator-kb` repo's `research/`
directory, kept separately since it's forensic/derivation detail rather
than something this skill needs at use-time.
