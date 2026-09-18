# Manifest (sample sheet) format

## File format

- **Delimiter is auto-detected from the first line only**: whatever
  non-word character immediately follows the first run of word-characters
  in the header line (space, tab, comma, or newline). That same character
  is then used to split **every** line of the file with a naive
  `str.split(delim)` — no quoting, no escaping. A value cannot itself
  contain the delimiter character.
  - `sample\tfile\tgroup` (tab), `sample,file,group` (comma), and
    `sample file group` (space) all auto-detect correctly.
  - A header like `"sample id",file` breaks auto-detection, since a quote
    character (not the intended delimiter) immediately follows `sample`.
    Keep column names as single alphanumeric/underscore words with no
    embedded punctuation right after the first word.
- First line = column headers; every following line = one data row.
- Every row must have the same number of fields as the header, or the
  whole run fails to parse.
- Column name matching is case-insensitive everywhere.

## Supplying a manifest to a script

Three mutually-exclusive-in-spirit mechanisms, pick one per script:

1. **Sheet file(s) on the command line** (default, when the script's setup
   header has no `##argv=` and no setup-script body): `myscript
   [rms-options] sheet1.txt [sheet2.txt ...]`. Use this when the user is
   expected to hand you an existing sample sheet file.
2. **`##argv=<usage string>`**: the script takes plain positional args
   instead of sheet files; each arg becomes one row of a synthetic
   single-column manifest (column name is whatever the usage string
   implies — conventionally `sample`, since args are usually sample
   directory names/paths). Use for scripts whose "manifest" really is just
   "the list of sample directories I was given," with no other per-sample
   metadata needed.
3. **`##sheet=EOF ... EOF` inline block**, either static in the setup
   header or (far more common in practice) emitted by a setup script's own
   stdout after it reads/transforms a user-supplied file. This is the
   dominant pattern when the script needs custom CLI flags (genome choice,
   comparison groups, etc.) alongside the sample table — see
   `idioms.md`'s "sample-sheet passthrough" pattern.

## Multiple sheets / joining

- Multiple sheet sources (files and/or inline `##sheet=` blocks) merge
  column-wise.
- The first sheet parsed defines the canonical column set.
- Every subsequent sheet **must share the same first-column name** as the
  first sheet, and gets **left-joined** onto it by matching that
  first-column value (rows with no match get empty-string-filled columns).
  This is how you support "one sheet has the base sample list, another
  sheet adds extra per-sample columns."
- A column name that collides across sheets (or with a declared `##`
  pipeline variable) is a fatal error — don't reuse names.

## Pipeline variables as pseudo-columns

A setup-header `##NAME=(v1 v2 v3)` directive (parens required — see
`grammar.md` §3 and `engine_quirks.md`) behaves exactly like an extra
manifest column whose "rows" are the listed literal tokens: it participates
in step grouping and template substitution the same way a real sheet column
does. Distinct pipeline variables get cross-joined as a Cartesian product
against real manifest-column groupings when both appear in the same step's
grouping list.

## Practical guidance for designing a manifest

- Default first column to `sample` unless there's a genuinely different
  natural key for the whole pipeline (`bamfile`, `file`, `experiment`) —
  matches every real script surveyed.
- If a step needs to run once per (sample × sub-unit) — per lane, per
  genomic region, per FASTQ chunk — add that sub-unit as its own column
  (e.g. `regionBySize`) rather than trying to encode it into `sample`
  itself, and grade that step's grouping as `sample,regionBySize`. This is
  how James Knight's fine-grained exome/genome pipelines parallelize below
  the sample level.
- Reserve `experiment`/`comparison`-style columns for steps that
  aggregate/compare across multiple samples — group those steps on that
  column (or `all`) instead of `sample`.
