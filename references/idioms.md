# Reusable idioms from production `.rms` scripts

Patterns proven in Dejian Zhao's (DZ) and James Knight's (JK, the RMS
author) real, working scripts. Reuse these rather than inventing new
shapes for the same problem. Full gold-reference scripts are in
`../assets/`.

## Header skeleton

```
#!/usr/bin/env rms

##python

import sys, argparse

parser = argparse.ArgumentParser()
parser.add_argument('--ref', required=True, help='genome reference code')
parser.add_argument('--sheet', required=True, help='path to sample sheet')
# this is just examples to grow argument list
# parser.add_argument('--comparison', default=None, type=str, help='comparison file')
args = parser.parse_args()

genome = {}
genome['hg38'] = "/path/to/hg38/index"
genome['mm10'] = "/path/to/mm10/index"
sys.stdout.write("##ref=( %s )\n" % genome[args.ref])

sheetContent = open(args.sheet)
sys.stdout.write("##sheet=EOF\n")
sys.stdout.write(sheetContent.read())
sys.stdout.write("EOF\n")

##env
module purge
module load Tool/Version-toolchain
export RMSHOME="/home/dz288/rms"
```

Use `argparse` with `--long-options` for scripts a human will invoke with
memorable flags (DZ's convention, and the friendlier one for anyone other
than the RMS author reading `--help`). Reserve a bare `##argv=sample`
header for genuinely simple scripts that just take a list of sample
directories with no other options.

## Sample-sheet passthrough (near-universal)

When the script's real job needs custom args but the sample list itself
comes from a user-supplied file, don't reparse it into memory — read and
re-emit verbatim:
```python
sheetContent = open(args.sheet)
sys.stdout.write("##sheet=EOF\n")
sys.stdout.write(sheetContent.read())
sys.stdout.write("EOF\n")
```

When the script should discover samples itself instead (scanning a
directory tree rather than trusting a user file), build the sheet
programmatically:
```python
sys.stdout.write("##sheet=EOF\n")
sys.stdout.write("Sample Bamfile\n")
for arg in sys.argv[1:]:
    sample = os.path.basename(arg).replace(".bam", "").replace(".cram", "")
    sys.stdout.write("%s %s\n" % (sample, arg))
sys.stdout.write("EOF\n")
```
(full version in `../assets/gold_bam2fastq_JK.rms`)

## Genome-dispatch dict

Resolve every genome-dependent path **once**, in the setup-header Python
preamble, from a single `--ref`-style flag — never hardcode a genome path
inside a step body:
```python
genome = {}
genome['hg38'] = "/path/to/hg38/star_index"
genome['mm10'] = "/path/to/mm10/star_index"
if args.ref not in genome:
    sys.stderr.write("Error: unknown --ref %s\n" % args.ref)
    sys.exit(-1)
sys.stdout.write("##refpath=( %s )\n" % genome[args.ref])
```
Add a new genome by adding a dict entry, never by editing step bodies.

## Fail-fast genome/reference validation as the first step

Before any real work, verify the resolved reference actually exists on
disk — catches a stale/renamed reference path immediately instead of many
steps into a run:
```
#### DoubleCheck all -
##ppn=1
if [ ! -f <gtf> ]; then
	echo "Error: GTF not found: <gtf>" >&2
	exit 1
fi
```
(Real gotcha from production: an author once spent time debugging an
apparent tool bug that turned out to just be a stale reference path after
a file rename — a `DoubleCheck` step like this would have caught it
immediately.)

## PE/SE lane detection and merge (the single most copy-pasted block)

Detecting paired-end vs single-end reads and merging multiple lane files
for one sample, inside a step body:
```bash
FQ=""
cntFQ=0
for R1 in <sample>/Unaligned/*_R1_*.fastq.gz
do
	cntFQ=$(($cntFQ+1))
	R2=${R1/_R1_/_R2_}
	if [ -e $R2 ]; then
		FQ="$FQ $R1 $R2 "
	else
		FQ="$FQ $R1"
	fi
done
```
Equivalent glob-no-match-guard idiom (JK's variant, needed because an
unmatched bash glob leaves the pattern string literal rather than empty):
```bash
gzfiles=`echo <sample>/Unaligned/*_R1_*.fastq.gz`
if [ "$gzfiles" == '<sample>/Unaligned/*_R1_*.fastq.gz' ] ; then gzfiles='' ; fi
```

## Cross-sample aggregation with `glob=True`

An `all`- or `experiment`-grouped step collecting every sample's output
without listing samples individually:
```
#### collectResults all Reports/results.tar.gz
##ppn=1
RESULT="Reports/results"
mkdir -p $RESULT
rsync -a <sample,glob=True>/QC/*.html <sample,glob=True>/QC/*.pdf $RESULT
tar -czvf ${RESULT}.tar.gz $RESULT && rm -rf $RESULT
```

## Building a repeated-flag argument list (JK idiom)

For tools that want a flag repeated once per file (e.g. GATK's `-I`):
```
gatk GatherBQSRReports \
   <sample>/<sample>.recal.<regionBySize,glob=true,prefix="-I ">.table \
   -O <sample>/<sample>.recal.table
```

## Optional pipeline branch via in-body guard, not RMS-level conditionality

RMS has no step-level "only run if" directive beyond the narrow
`##KEY=... if COL=VAL` template-variable lookup — for a whole optional
branch (e.g. "only do this if the user asked for a comparison"), guard the
step body itself:
```bash
if [ "<doComparison>" != "True" ]; then
	exit 0
fi
```
where `<doComparison>` is a pipeline variable emitted from the setup-header
Python preamble as `##doComparison=( True )` or `##doComparison=( False )`
based on whether the relevant CLI flag was given.

## Local-disk staging with `rmscp`/`rmssync` (JK idiom, for I/O-bound steps only)

```
##local=6x<sample>/<sample>.bam
##io=4
rmssync --bwlimit=50000 <sample>/<sample>.bam <local>/
gatk SomeRegionTool -I <local>/<sample>.bam -O <local>/<sample>.out.bam ...
rmssync --bwlimit=50000 <local>/<sample>.out.bam <sample>/
```
Only reach for this when `resources_and_staging.md`'s decision tree
actually calls for it (small-file/random-access I/O pattern) — most steps
should operate directly on GPFS paths.

## Defensive existence checks after critical operations

```bash
[ -e <sample>/<sample>.bam.bai ] || exit -1
```

## In-body idempotency guard distinct from RMS's own checkFile

When a step has sub-parts that need finer-grained skip logic than one
checkFile can express:
```bash
if [ -e <sample>/<sample>.bam ] ; then
	exit 0
fi
```

## Dated inline changelog comments

Both authors treat the `.rms` file itself as a running changelog for
non-trivial parameter changes, rather than keeping a separate log:
```
# added [2026-5-31 Sun]: spikeNormBW step for spike-in normalization
```
When editing an existing production-style script (not a fresh one-off),
follow this convention rather than silently changing behavior.

## Optional completion-notification step (DZ idiom)

```
#### sendEmail all .sendEmail.done
CC="user@yale.edu"
email="Pipeline complete."
echo "$email" | mail -s "pipeline - done" -S "from=Name <user@yale.edu>" -c $CC $CC
touch .sendEmail.done
```
Offer this as an optional final step, don't add it unasked.
