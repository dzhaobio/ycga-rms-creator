# CLI invocation and McCleary environment facts

## `rms` binary

Live path on McCleary (expected on `PATH`):
`/gpfs/gibbs/pi/ycga/mane/ycga_bioinfo/bin_May2023/rms`
(the source directory read for this skill's research was
`/gpfs/gibbs/pi/ycga/mane/ycga_bioinfo/soft/rms_May2023/` — `bin_May2023`
is the installed/on-PATH counterpart). Run `rms -v`/`rms -h` if unsure of
the currently deployed version/flags rather than trusting this note
indefinitely.

A `.rms` file with `#!/usr/bin/env rms` as its first line can be run
directly (`./myscript.rms args...`) or explicitly (`rms myscript.rms
args...`).

## Global `rms` flags

| Flag | Long form | Effect |
|---|---|---|
| `-t` | `--test` | Compile-only: syntax-check generated scripts without running them |
| `-s` | `--single` | Run all commands sequentially on the current machine |
| `-p` | `--parallel` | Run on the current machine using all detected cores |
| `-c` | `--cluster` | Submit across the cluster (**default** mode) |
| `-f` | `--force` | Ignore existing checkFiles; force full re-run |
| `-S step` | `--start=step` | Start at named step, skip earlier ones |
| `-E step` | `--end=step` | End at named step, skip later ones |
| `-O step` | `--only=step` | Equivalent to `-S step -E step` |
| `-o dir` | `--output=dir` | Output dir / script CWD (default `.`) |
| `-l prefix` | `--log=prefix` | Log to `prefix.stdout`/`prefix.stderr` (`-` = direct to terminal) |
| `-n spec` | `--num=spec` | Node/core limit, or `queue[:#],queue2[:#2],...` |
| `-q file` | `--queue=file` | **No-op in this build** — see `engine_quirks.md` |
| `-h` | `--help` | Usage |
| `-v` | `--version` | Print version |

If a script's setup header has no custom argument processing (no
`##argv=`, no setup-script body), everything after the script name on the
command line is `[rms-options] sheet...` (one or more manifest files). If
the script *does* define custom processing, everything after the script
name is instead handed to that script's own argument parser.

## Known-good queue nicknames on McCleary (from `rmsrc`)

`-n ycgak,ycgalk` is the default queue-flag combination used in existing
production runs — both map to SLURM partition `ycga` (account `mane`) with
different internal ppn/mem/QOS profiles. Confirm current queue names with
whoever owns the `rmsrc` file if a run needs an unusual resource profile;
don't assume other nicknames exist without checking.

## Companion CLI tools

- **`rmslock`**: generic `flock`-wrapper — runs its arguments while
  holding an exclusive lock on a per-worker lockfile in
  `$RMS_STEP_LOCAL_DIR`. Used to serialize concurrent access to shared
  local scratch resources.
- **`rmscp`**: `rmslock cp $*` — flock-guarded `cp`.
- **`rmssync`**: `rmslock rsync $*` — flock-guarded `rsync`. The standard
  way to stage files into/out of `<local>` safely when multiple concurrent
  step-commands on the same worker might race on a shared file (see
  `idioms.md`'s local-staging pattern).
- **`rmsRemoteWorker`**: not user-invoked directly — the worker-node
  executable RMS's scheduler submits via `sbatch`.

## Validating before handing back a draft

1. Run `python3 scripts/validate_rms.py <path/to/script.rms>` (this
   skill's own linter — see `SKILL.md`) for structural/template-variable
   checks the real `rms` binary won't catch until much later (or won't
   catch at all, in the case of silently-unresolved `<name>` tokens).
2. Where the `rms` binary is actually reachable, run a real compile check
   with a small (1-2 row) test manifest:
   `rms -t myscript.rms --ref <code> --sheet tiny_test_sheet.txt` (adjust
   args to the script's own header). This exercises the setup-header
   script (if any) and the parser/checker for real, catching anything the
   static linter can't (e.g. a setup script that itself errors, or a
   language-specific syntax error inside a step body).
3. If a live manifest/genome isn't available to fully test end-to-end,
   `-t` compile mode still validates pipeline structure and script syntax
   without needing real data to complete — prefer it over skipping
   validation entirely.
