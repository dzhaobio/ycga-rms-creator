# RMS `.rms` script grammar — authoritative reference

Distilled from reading the installed engine source at
`/gpfs/gibbs/pi/ycga/mane/ycga_bioinfo/soft/rms_May2023/` (version string in
`arguments.py`: `"RMS, version 0.9.0"`) directly, not from the (incomplete,
occasionally inconsistent) Sphinx docs at rms.readthedocs.io. Where the docs
and the engine source disagree, this file follows the engine source — see
`engine_quirks.md` for the specific disagreements found. This is a portable
reference for authoring correct scripts; it doesn't cite line numbers (that
level of detail, if ever needed again, lives in the `ycga_rms_creator`
project's `research/01_engine_grammar.md`).

## 1. Top-level file structure, in strict order

```
#!/usr/bin/env rms          (optional shebang)
<setup header>              (always present, possibly empty)
##env                       (optional, at most one block)
<env header lines>
##init [lang]                (optional, can repeat, one per language)
<init header lines>
#### Step1 grouping1 checkFile1
<step1 body>
#### Step2 grouping2 checkFile2
<step2 body>
...
```

The parser is line-oriented (regex + `.startswith()`, no tokenizer). `#### `
(four `#` + a space) always starts a new step and ends whatever came before
it. `##env` and `##init` are recognized only in the setup-header region,
before the first step.

## 2. The three kinds of `##`/`#` lines — get this exactly right

- `##key=value` (two hashes, **no space** before `key`) → a directive the
  parser consumes. Never appears in the generated script.
- `## some text` (two hashes, **then a space**) → an ordinary comment,
  passed through verbatim into the generated script/header.
- `#some text` (one hash) → also passed through verbatim (bash-comment
  syntax). Same treatment as `## text`.

Any line starting `##` with no space, that doesn't match a recognized
directive, is a **fatal parse error** — there is no generic "unknown
directives are ignored" fallback. Double-check directive spelling.

## 3. Setup header

Everything from the top of the file (after an optional shebang) up to the
first `#### `, `##env`, or `##init` line. Recognized directives, order
matters for `##lang`/`##bash`/`##perl`/`##python`/`##R` (must come first if
present):

| Directive | Effect |
|---|---|
| `##lang=bash\|perl\|python\|R` | default scripting language for step bodies that don't set their own `##bash`/`##perl`/`##python`/`##R` |
| `##bash` / `##perl [args]` / `##python [args]` / `##R [args]` | language of the *setup script itself* (not step default) |
| `##sheet=MARKER` ... `MARKER` | inline manifest, heredoc-style, terminated by a line starting with `MARKER` (any word works as the marker, `EOF` is conventional) |
| `##option="..."` | literal option string RMS uses to re-parse the script's own CLI args a second time |
| `##argv=<usage string>` | script takes positional args instead of sheet filenames; each arg becomes one row of a synthetic single-column manifest. Mutually exclusive with writing setup-script body lines (fatal error if both) |
| `##vol=...` | Docker volume mapping for the *setup script's own* container (rarely used — see `engine_quirks.md`) |
| `##redo=N` | pipeline-wide default retry count, inherited by every step (see `engine_quirks.md` — does not actually retry in this engine build) |
| `##outline=N` / `##errline=N` | default stdout/stderr line-count cap for logging, all steps |
| `##totalio=N` | global I/O throttle budget shared across all steps' `##io=` weights |
| `##NAME=(v1 v2 v3)` | declares a **pipeline variable** — a pseudo manifest column whose "rows" are the literal listed tokens. Participates in step grouping and template substitution exactly like a real manifest column. **The value MUST be parenthesized** — `##name=col` (no parens) is a fatal parse error, not a valid directive (see `engine_quirks.md`, this contradicts one docs example) |

Any other line (no leading `##`) is literal setup-script body text. If the
setup header has any non-comment/non-blank body lines, RMS actually
**executes that script** (bash/perl/python/R, per `##bash`/etc.) before
continuing, and re-parses its **stdout** as more setup-header directives.
This is the standard way to: build a genome-lookup dict from a `--ref` flag
and emit `##refver=(...)`-style variables, or read a user-supplied sheet
file and re-emit it as `##sheet=EOF ... EOF`. See `idioms.md`.

## 4. Env header (`##env`)

A bare `##env` line starts it. Contents:
- `##local=<remotepath> [localname]` — stage a file into
  `$RMS_STEP_LOCAL_DIR` (via `rmscp`) before any step runs on a worker.
  Rare; most local-disk staging happens per-step instead (see
  `resources_and_staging.md`).
- Any other `##...` line here is a fatal error.
- Everything else (module loads, `export`s, `mkdir -p` for shared dirs) is
  literal shell prepended **verbatim into every generated script** — the
  setup script's own launcher AND every step script. This is where you put
  the pipeline-wide `module load ...` / `source $CONFIG/tool-version` lines.

## 5. Init header (`##init [lang]`)

Can repeat, once per language (`bash|perl|python|R`). Lines here get
inserted **before** each step's own script body, for steps written in that
language — use for `import`s, R `library()` calls, `use strict;`, etc. that
every step of that language needs.

## 6. Step blocks

### 6.1 Step header line — exactly 4 whitespace-separated fields

```
#### <stepName> <groupCol1[,groupCol2,...]|all> <checkFile>
```

- `stepName`: must be unique across the whole file (case-sensitive compare).
- grouping: comma-list of manifest column names (case-insensitive, stored
  lowercased) that this step is parallelized/looped over — OR the literal
  keyword `all` (must be the *sole* token) meaning "run once, ungrouped,
  over every manifest row." **There is no explicit loop keyword** — naming
  a column as the grouping key is what makes RMS spawn one instance of the
  step per distinct value (or value-combination, for multi-column grouping)
  of that column actually present in the manifest.
- `checkFile`: a path (subject to template substitution, §8) whose
  existence — after substitution — marks that step instance as already
  done. Pure existence test; see `engine_quirks.md` for what this does and
  doesn't guarantee.

A line with anything other than exactly 4 fields (e.g. a checkFile path
containing an unescaped space) is a fatal parse error.

### 6.2 Step body

A mix of:
- **Step option lines** (bare `##key=value`), which can appear interleaved
  anywhere in the body (unlike the header, there's no "must come first"
  ordering requirement inside a step).
- **Literal script lines** — the actual bash/perl/python/R for this step.

Recognized step options:

| Directive | Effect |
|---|---|
| `##bash` | this step's script is bash (also the implicit default if nothing is set); takes no trailing args |
| `##perl [args]` / `##python [args]` / `##R [args]` | language for this step; trailing text becomes interpreter args |
| `##ppn=N` | cores/slots this step instance needs |
| `##mem=N` | memory in GB |
| `##io=N` | I/O weight; contributes `1/N` to a shared I/O throttle budget |
| `##local=<spec>` | scratch space (GB) reserved in `$RMS_STEP_LOCAL_DIR`: a plain integer, an `Nx` multiplier applied to a referenced file's size (`4x<file>`), a literal file path (uses that file's size), or a comma list of paths (sums sizes) |
| `##tmp=<value>` | a file to copy into `$RMS_STEP_TMP_DIR` before the script runs (repeatable) |
| `##after=<step1,step2,...>` | explicit dependency — see §7 |
| `##outline=N` / `##errline=N` | per-step override of the setup-header defaults |
| `##redo=N` / `##redo=:cmd` / `##redo=N:cmd` | retry count / cleanup-command syntax — **parsed but does not actually retry anything at runtime in this engine build**; see `engine_quirks.md` |
| `##boxer=<container>` / `##docker=<image>` / `##vol=<mapping>` | alternate container runtime — **parsed but inert (never wired into script generation)** in this engine build; see `engine_quirks.md` |
| `##<key>=<value> if <col>=<val>` | conditional value lookup — defines template variable `<key>` from manifest column `<value>`, evaluated as if the manifest were filtered to `col=val`. Used to pull a value from a *different* row/branch than the one driving the current step instance |

Any `##key=value` step-option line that doesn't match one of the above, and
doesn't contain the literal substring `" if "`, is a **fatal parse error**
("Invalid pipeline step option") — including things a docs page might
mention that the installed engine doesn't actually implement (`##qc`,
`##name=`; see `engine_quirks.md`).

An empty step script body (no `##`-option-only step) produces a warning,
not a fatal error, at pipeline-check time.

## 7. Dependency model

- **No `##after=` given** → the step implicitly depends on the single
  immediately-preceding step in file order. Steps form a default linear
  chain top-to-bottom.
- **`##after=stepA,stepB,...`** → overrides the default entirely (not
  additive). Depends only on the named steps. Names are resolved
  case-insensitively against steps **already defined earlier in the
  file** — forward references are a fatal error.
- At the Command level (one step × one grouping-value instance), a
  downstream Command depends on all upstream Commands whose manifest
  row-range intersects its own — this is what lets a per-sample step
  correctly wait only on its own sample's upstream work, while an
  `all`-grouped step (whose range spans every row) waits for every upstream
  instance.
- If a step's dependency is genuinely conditional (only relevant for some
  rows/some run modes) rather than structural, that's expressed **inside
  the step body** with a shell early-exit guard on a flag variable, not
  through RMS's own dependency syntax — see `idioms.md`.

## 8. Template substitution (the "macro language")

This is the *only* macro/function system RMS provides inside step script
text — there is no other built-in command library. Regex-based, applied to:
step script bodies, step script interpreter args, the `##local=` spec
string, and the `checkFile` path.

```
<NAME>
<NAME,option=value,option2="quoted value",...>
```

`NAME` resolves (in priority order) against: a step-option lookup value
(from `##KEY=... if COL=VAL`), a "cmd lookup" built-in (`tmp`, `perm`,
`local`, `ppn` — see §8.3), a manifest column, or a declared pipeline
variable (`##NAME=(...)`). Matching is case-insensitive.

**If `NAME` isn't found in any of those sources, `<NAME...>` is left
completely unmodified in the output — this is a silent no-op, not an
error.** A typo in a template variable name will not be caught at
parse/build time; it surfaces later as literal `<typo'd_name>` text handed
to the shell (usually a confusing "command not found" or "no such file"
downstream). Always double-check spelling of every `<...>` token against
what you actually declared.

If `NAME` resolves to multiple values (e.g. several fastq files for the
current sample), the substitution expands to **all** of them, each wrapped
by `prefix`/`suffix`/`quote`, joined by `sep`.

### 8.1 Options (comma-separated inside `<...,...>`)

| Option | Effect | Default |
|---|---|---|
| `prefix=STR` | prepended to each value | `""` |
| `suffix=STR` | appended to each value | `""` |
| `sep=STR` | separator between multiple values | `" "` |
| `quote=CHAR` | wraps each `prefix+value+suffix` unit | `""` |
| `glob=true\|false` | also swallow non-whitespace text immediately touching the tag on either side into the substitution (so `path/<sample>.txt` treats the whole path as one glob-able unit rather than just the tag) | `false` |

Option values are a bare word or a quoted string (spaces/special chars
allowed inside quotes). An unrecognized option name is a hard runtime
error.

Worked example: `<fastq,prefix="--in ",quote='"'>` with `fastq` = `a.fq.gz`,
`b.fq.gz` for the current partition expands to:
`"--in a.fq.gz" "--in b.fq.gz"` (quote wraps the whole prefix+value+suffix
unit, not just the bare value).

### 8.2 `glob=True` — the cross-sample aggregation idiom

`<sample,glob=True>` is the standard way for an `all`-/`experiment`-scoped
step to glob across every sample's per-sample output without listing
samples individually, e.g.:
```
rsync -a <sample,glob=True>/FastQC/*.html $RESULT
```
This expands `<sample>` to every distinct sample value and glob-swallows the
adjoining path text, producing one whole path-with-wildcard per sample.

`<var,glob=True,sep=",",prefix="-I ">` is used to build a whole
repeated-flag argument list for tools that want it (e.g. GATK's
`-I file1 -I file2 ...`) — the substitution mini-language can build entire
CLI fragments, not just single path substitutions.

### 8.3 Special "cmd lookup" tokens

Always available inside a step's script body/args (not in the setup or env
headers), regardless of manifest content:

| Token | Resolves to |
|---|---|
| `<tmp>` | `$RMS_STEP_TMP_DIR` — per-command scratch dir, deleted after the command finishes |
| `<perm>` | `$RMS_STEP_PERM_DIR` — per-command dir whose contents get copied to the final output dir if used |
| `<local>` | `$RMS_STEP_LOCAL_DIR` — the worker-persistent local scratch dir where `##local=`-staged files live |
| `<ppn>` | this step's own `##ppn=` value, as a literal string (e.g. for `--threads <ppn>`) |

These three directories are also exported by name (`$RMS_STEP_TMP_DIR`,
`$RMS_STEP_PERM_DIR`, `$RMS_STEP_LOCAL_DIR`) at the top of every generated
bash script, so plain bash can reference them directly instead of the
`<...>` tag — the tag form is what non-bash languages and non-shell
contexts (the `checkFile`/`##local=` strings) need instead.

## 9. What every generated script actually runs under

- Bash scripts run with `set -o errexit -o nounset -o pipefail`. Any
  non-zero exit, any reference to an unset variable, or any failing command
  mid-pipe aborts the step immediately. Write step bodies accordingly —
  don't rely on an unset variable defaulting to empty, and know that `cmd1
  | cmd2` fails the step if *either* command fails, not just the last one.
- Non-bash languages (`##perl`/`##python`/`##R`) are still driven from a
  bash wrapper script, not a direct shebang exec.
- The `.rms` file's original line numbers are preserved (via blank-line
  padding) in the generated script, so error messages/stack traces from a
  failed step map back fairly directly to the source `.rms` file.

## 10. Hard limits

- A `.rms` script file over 1,000,000 bytes is rejected outright.
- A manifest sheet file over 1,000,000 bytes is rejected outright.
- No `#include`/import for other `.rms` files exists — a script is always
  fully self-contained.

## 11. Manifest/sheet format

See `manifest.md` for the full sheet-parsing rules (delimiter
auto-detection, multi-sheet joining, `##argv=`-synthesized sheets).
