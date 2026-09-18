---
name: ycga-rms-creator
description: Write, extend, or review .rms pipeline scripts for Yale YCGA's RMS ("Run My Samples") SLURM job-orchestration DSL on McCleary. Use when asked to write a new RMS script for a bioinformatics workflow, add or modify a step in an existing .rms file, port a by-hand or another-tool's pipeline into RMS, or review/debug a draft .rms script -- as distinct from *running* an already-built RMS-based service (see the ycga-rnaseq-deg / ycga-rnaseq-deg-as skills for that). Covers script grammar, manifest/sheet design, step sequencing and dependency wiring, per-step resource and local-disk-staging decisions, reusable idioms from Dejian Zhao's and James Knight's production scripts, and validating a draft before handing it back.
---

# Authoring RMS pipeline scripts

RMS is a line-oriented DSL + SLURM-backed scheduler: a `.rms` file declares
a sample manifest, an environment header, and a sequence of steps, each of
which is parallelized by grouping over manifest columns rather than an
explicit loop keyword. There's no function-call/built-in-command layer
inside step bodies beyond a template-substitution mini-language (`<NAME,
opt=val,...>`) -- step bodies are otherwise plain bash/perl/python/R.

Read `references/grammar.md` before writing anything nontrivial -- it's
the precise, authoritative spec (read from the installed engine source,
not just the docs, which have some gaps and one outright wrong example).
This file is the workflow/decision procedure; the `references/` files are
the detail you'll actually need while writing.

## The authoring workflow

1. **Clarify the task's shape** before touching syntax: what's the actual
   tool chain (QC → trim → align → ... )? What's the natural manifest key
   (`sample`, `experiment`, `bamfile`, something composite)? Is there
   more than one genome/species to support? Are there existing scripts for
   this assay type to base structure on (check `/home/dz288/rms/*.rms` and
   `/home/dz288/rms/rms_JamesKnight/*.rms` for a close relative before
   starting from scratch)? If any of this is genuinely unclear or
   unstated, ask rather than guessing -- a wrong manifest key or step
   sequence is expensive to unwind later.

2. **Decide the manifest/header approach** (`references/manifest.md`):
   - Simple positional sample-directory list, no other options needed →
     bare `##argv=sample`.
   - Needs custom CLI flags (genome choice, comparison groups, etc.) but
     the sample list comes from a user-supplied sheet file → `##python`
     preamble with `argparse`, passing the sheet through verbatim as
     `##sheet=EOF ... EOF` (see `idioms.md`).
   - Needs to discover samples itself (scan a directory tree, derive from
     BAM/CRAM filenames, etc.) → build the sheet programmatically in the
     preamble instead of reading a user file.

3. **Enumerate steps and pick a grouping column for each one**, not once
   for the whole script. Most steps group by `sample`; steps that
   aggregate/compare across samples group by `experiment`/`comparison`/
   `all`; steps that need to parallelize *below* sample level (per-region,
   per-chunk) need a dedicated manifest column of their own. This is the
   single most important design decision per step.

4. **Wire dependencies.** Default to file order (steps run top-to-bottom,
   each depending on the one above) wherever that already matches the
   real dependency. Add explicit `##after=stepA,stepB` only where a step
   genuinely needs to fan in from multiple upstream branches, or skip
   over an intermediate step it doesn't actually depend on. Remember:
   `##after=` only allows backward references (steps already defined
   earlier in the file) and *overrides* the default chain entirely rather
   than adding to it.

5. **Assign resources and local-disk staging per step**, using the
   decision tree in `references/resources_and_staging.md` -- based on
   what *that step* does (light/CPU-bound/JVM-heavy/fan-in), not a single
   style adopted for the whole script. This is a deliberate choice: reuse
   whichever author's convention (Dejian's GPFS-direct style or James
   Knight's local-staging-with-`rmssync` style) actually fits each step's
   I/O profile.

6. **Write step bodies using the proven idioms** in `references/idioms.md`
   rather than inventing new shapes for the same problem (PE/SE lane
   detection and merge, genome-dispatch dict, fail-fast reference-path
   check, cross-sample `glob=True` aggregation, optional-branch guards).
   Gold-reference full scripts are in `assets/`.

7. **Validate before handing it back** -- see "Validating a draft" below.
   Do this every time, even for a short script; the most dangerous class
   of bug (an unresolved `<name>` template token) is silent at every other
   stage.

8. **Placement.** Don't drop a finished script directly into
   `/home/dz288/rms/` (Dejian's curated personal library) unless
   explicitly told to -- that's a meaningful, persistent action. Default
   to writing it into the current project/working directory as a draft,
   and say where you put it.

## Must-know engine quirks (full detail: `references/engine_quirks.md`)

- `##redo=` is parsed but **never actually retries anything** on this
  engine build. Don't promise retry behavior.
- `##docker=` / `##boxer=` / `##vol=` as step options are parsed but
  **inert** -- they never wrap the generated script in a container.
- `##qc` step sub-blocks are **not reachable syntax** -- the parser path
  that would handle them is disabled. Use an ordinary extra step instead.
- `rms -q/--queue` is a **no-op** -- the queue config file is always the
  `rmsrc` installed alongside the `rms` binary.
- The docs mention a step option `##name=column`; **this does not exist
  in the installed engine and will fatal-error.** Compute distinct values
  yourself in the setup-header preamble and emit a proper
  `##var=(val1 val2 ...)` (parens required) instead.
- **An unresolved `<name>` template token is left as literal text, not an
  error.** This is the single easiest way to ship a broken script that
  looks fine until it runs. Always run the validator (below).
- `checkFile`-based resume is pure existence-check, no timestamp/content
  comparison -- a stale leftover file can cause a step to be wrongly
  skipped.
- Only `torque`/`lsf`/`slurm` backends actually work; every live YCGA
  McCleary config uses `slurm`. One SLURM job = one long-lived RMS
  "worker" that bin-packs many steps' commands, not one job per step.

## Validating a draft

1. **Always** run the skill's own linter first:
   ```
   python3 scripts/validate_rms.py path/to/draft.rms
   ```
   It checks structural rules the real parser enforces (unique step
   names, no forward `##after=` references, exactly-4-field step headers,
   recognized step options, the `##argv`+script-body conflict) *and*
   things the real parser won't ever flag (unresolved `<name>` tokens,
   use of the inert/dead directives above). It cannot see manifest
   columns that a `##python`/bash preamble builds dynamically rather than
   embedding as a literal `##sheet=EOF...EOF` block -- if a script uses
   that pattern, you'll get a batch of column/template warnings that are
   expected false positives; read them, cross-check the names by eye
   (they should match whatever the preamble's `sys.stdout.write(...)`
   calls actually emit), and move on rather than trying to silence them.
2. **Where the real `rms` binary is reachable**, also do an actual
   compile check with a tiny (1-2 row) test manifest -- see
   `references/cli_and_environment.md` for the exact invocation and the
   live binary path. This exercises the setup-header script for real and
   catches anything the static linter can't (a preamble that itself
   errors, a language-specific syntax error inside a step body). Prefer
   `-t`/`--test` mode so this doesn't require real data or submit
   anything to the cluster.
3. Sanity-read the step-by-step dependency chain once more by eye:
   does each step's default (file-order) dependency actually make sense,
   or does something further down secretly need an explicit `##after=`?

## Reference index

- `references/grammar.md` -- the full script grammar (load this first for
  anything nontrivial).
- `references/manifest.md` -- sample sheet / manifest format and how to
  supply one.
- `references/resources_and_staging.md` -- the per-step resource/staging
  decision tree and value tables from real production scripts.
- `references/idioms.md` -- reusable code snippets proven in production.
- `references/engine_quirks.md` -- dead/inert directives, silent-failure
  traps, and every place the docs and the installed engine disagree.
- `references/cli_and_environment.md` -- `rms` CLI flags, companion tools
  (`rmscp`/`rmslock`/`rmssync`), live McCleary paths and queue names.
- `assets/gold_bam2fastq_JK.rms`, `assets/gold_fastqc_JK.rms`,
  `assets/gold_fastq_screen_DZ.rms` -- short, clean, verbatim production
  scripts to pattern-match structure against.
- `scripts/validate_rms.py` -- the static linter described above.

## Provenance

Built 2026-09-18 from a three-way research pass (installed engine source
at `/gpfs/gibbs/pi/ycga/mane/ycga_bioinfo/soft/rms_May2023/`, the official
docs at rms.readthedocs.io, and a survey of Dejian Zhao's and James
Knight's production `.rms` scripts). The full forensic research --
file/line citations, quantitative directive-frequency tables, and the
doc-vs-engine reconciliation notes -- lives in the `ycga_rms_creator`
project's `research/` directory if anything here ever needs
re-verifying against a different RMS build/version.
