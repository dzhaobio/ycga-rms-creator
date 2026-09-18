# Engine quirks, dead code, and doc/engine disagreements

Everything here was confirmed by reading the installed engine source at
`/gpfs/gibbs/pi/ycga/mane/ycga_bioinfo/soft/rms_May2023/` directly. Where
the official docs (rms.readthedocs.io) say something different, this file
notes it — **trust the engine source**, since that's what actually runs on
McCleary. Full forensic detail (file/function/line citations) is preserved
in the `ycga-rms-creator-kb` repo's `research/01_engine_grammar.md` and
`research/00_reconciliation_notes.md` if this ever needs re-verifying
against a different RMS build.

## Directives that are parsed but do nothing at runtime — don't rely on them

- **`##redo=N` / `##redo=:cmd` / `##redo=N:cmd`** (setup-header default or
  per-step). The parser fully implements this syntax, and `Step` objects
  carry `redoCnt`/`redoCmd` fields — but no code in `commands.py`,
  `ClusterController.py`, or `SingleController.py` ever reads those fields
  to actually retry a failed command. A failed step is marked `FAILED`
  and stays failed; there is no automatic retry loop in this build.
  **Don't tell a user this will retry anything.** If asked for retry
  behavior, either don't emit `##redo=` at all (simplest, most honest), or
  emit it with an explicit caveat that it's inert on this deployment.
- **`##docker=<image>` / `##boxer=<container>` / `##vol=<mapping>` as step
  options.** Parsed and stored on `Step`, but `script.py`'s script-writer
  has no Docker/Boxer logic at all — these never wrap the generated script
  in a container invocation. Same for the setup-header form of `##vol=`.
  Don't generate these; every step actually runs as a plain shell/perl/
  python/R script directly on the worker node.
- **`##qc` step sub-block.** The parser code for a per-step QC-script
  sub-section (its own `##bash`/`##perl`/`##python`/`##R`, own check file)
  is fully implemented but its call site inside the main step parser is
  commented out in this build. **`##qc` lines are not currently reachable
  syntax — do not emit them.** (If a user wants post-step QC, make it its
  own ordinary step with `##after=` instead.)
- **`rms -q/--queue <file>`.** Parsed as a CLI flag, but the code path that
  would actually use it is commented out — the queue config file is always
  hardcoded to the `rmsrc` file installed alongside the `rms` binary
  itself. There is no way to point a run at a different queue-config file
  from the command line in this build.

## A docs example that is actually invalid in this engine build

The official docs mention a step option `##name=column` ("creates new
variables from distinct column values"), listed alongside `##ppn`, `##mem`,
`##redo`, etc. **This does not match any directive the installed parser
recognizes.** `parseStepOption()`'s known-directive table has no `name`
key, and the fallback generic-variable syntax (`##KEY=(...)`) requires a
**parenthesized** value list — a bare `##name=column` (no parens) does not
match that pattern either. The practical result: writing `##name=column`
in a step will hit the parser's "Invalid pipeline step option" fatal error.
**Don't use it.** If you need a variable derived from distinct values of a
column, do it in the setup-header Python/bash preamble instead (compute the
distinct values yourself, emit `##yourvar=(val1 val2 ...)` from that
script's stdout — parenthesized, as `grammar.md` §3 requires).

## Silent-failure trap: unresolved template variables

`<NAME>` that doesn't resolve against any known source (manifest column,
pipeline variable, cmd-lookup token, step-option lookup) is left as literal
`<NAME>` text in the generated script — **not a parse error, not a runtime
error at generation time.** It only surfaces later as a confusing shell
error (or, worse, a command that "succeeds" while silently doing the wrong
thing, e.g. treating `<NAME>` as a literal filename). Before finalizing any
script, re-scan every `<...>` token used in step bodies/checkFile/`##local=`
against: the columns of whatever manifest this script will actually
receive, every `##NAME=(...)` pipeline variable you declared, the four
cmd-lookup tokens (`tmp`/`perm`/`local`/`ppn`), and any `##KEY=... if
COL=VAL` lookups defined in that same step. `scripts/validate_rms.py` does
this check mechanically — always run it before handing back a draft (see
`SKILL.md`).

## Resume/idempotency is existence-only

`checkFile` resume logic is a pure `os.path.exists()` test after template
substitution — **no timestamp or content comparison at all.** A stale
`checkFile` from a previous, now-outdated run will cause a step to be
silently skipped even if its real inputs changed. This is why production
scripts (see `idioms.md`) sometimes add their own in-body idempotency
guards distinct from RMS's own check-file mechanism, when a step's
sub-parts need independent, more precise skip logic than "does one file
exist."

## Failure propagates downstream without stopping the whole run

A failed command marks every downstream dependent as `SKIPPED` (not
separately failed) — the pipeline keeps running everything that *doesn't*
depend on the failure, then exits nonzero overall. Don't assume a
mid-pipeline failure halts everything; other branches keep going.

## Cluster backend: SLURM only, in practice

`torque`/`lsf`/`slurm` are the only reachable scheduler backends
(`submitSGEJob()`/`submitPBSJob()` exist in the source but are dead
code/unreachable). Every live YCGA McCleary `rmsrc` config uses
`type=slurm`. Architecturally, one SLURM job = one long-lived RMS "worker"
that RMS's own internal scheduler bin-packs many pipeline commands into
(by `ppn`/`mem`/`local`/`io`), communicating over a private TCP protocol —
**not** one SLURM job per pipeline step-instance. This matters when
explaining resource requests to a user: `##ppn=`/`##mem=` size a Command's
share of a worker's budget, not a standalone `sbatch` job's resources.

## Interrupt handling doesn't clean up in-flight cluster jobs

Ctrl-C stops RMS's own controller threads but does not cancel any
already-submitted SLURM worker jobs (no `scancel` call anywhere in the
codebase). If a run is interrupted, check `squeue` and cancel orphaned
worker jobs manually.
