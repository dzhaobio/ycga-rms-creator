# Per-step resource and local-disk-staging decisions

Resource directives (`##ppn=`, `##mem=`, `##io=`, `##local=`) are always
**per-step**, never pipeline-wide (aside from the setup-header's
`##totalio=` global throttle). Decide each step's directives from what that
specific step actually does — don't adopt one blanket convention for a
whole script. This is deliberate: real production scripts from both
Dejian Zhao (DZ) and James Knight (JK, the RMS author) mix conventions
within a single file depending on the step.

## Decision tree

1. **Is the step single-threaded and cheap** (flagstat, small Python/R
   post-processing, text munging, a single `awk`/`grep` pass)?
   → No resource directives at all, or at most `##ppn=1`. No local staging.

2. **Is the step a multi-threaded CPU-bound tool** (aligner, `cutadapt`,
   deepTools matrix/heatmap ops, `samtools sort -@`)?
   → `##ppn=N` matching the tool's own thread flag. Typical values seen in
   production: light aligners/tools `##ppn=4`; heavier splice-aware
   aligners or high-throughput steps `##ppn=8-16`. No `##mem=` unless the
   tool is also memory-hungry per thread. No local staging unless GPFS
   contention is a known problem for this specific tool.

3. **Is the step a JVM tool** (Picard, GATK)?
   → Set a real `##mem=` (production values cluster 14-40GB depending on
   the specific GATK/Picard operation; `MarkDuplicates`-style steps
   commonly use ~19GB). Then ask sub-question 3a:
   - **3a. Does it also do many small random-access reads/writes**
     (per-region BAM/VCF churn, e.g. `HaplotypeCaller`,
     `BaseRecalibrator` on split regions)?
     → Yes: add `##local=<spec>` (a flat GB number, an `Nx<file>`
       multiplier tied to a specific input's size, or a comma-list of
       input paths to sum) and stage in/out with `rmscp`/`rmssync`
       against `<local>`/`<tmp>` rather than operating directly on GPFS
       paths for the hot files. This is JK's signature idiom for the
       exome/genome pipelines — reach for it only when the step's I/O
       pattern actually justifies it, not by default.
     → No (a single big sequential read/write, e.g. whole-BAM
       `MarkDuplicates`): skip local staging even though it's a JVM tool.
       Operate directly on GPFS paths.

4. **Is the step a fan-in/aggregation step** (`experiment`- or
   `all`-grouped collection/reporting/tar-up step)?
   → Usually cheap (no resource directives), but check whether it needs
   `##after=stepA,stepB` naming multiple upstream steps explicitly — the
   default linear-chain dependency can't express "wait for every upstream
   per-sample branch to finish" on its own.

5. **Does the step decompress/read large FASTQ streams** (trimming,
   quality filtering)?
   → `##ppn=4` is the production norm; add `##io=N` if the deployment's
   queue config enforces an I/O throttle and this step is genuinely
   I/O-bound relative to others (JK convention; DZ's scripts mostly skip
   `##io=` even for trimming steps and rely on default throttling).

## Rough value reference from surveyed production scripts

| Tool category | `##ppn` | `##mem` (GB) | `##local`? |
|---|---|---|---|
| FastQC / flagstat / small stats | 1-2 (or omitted) | omitted | no |
| Trim Galore / fastp / cutadapt | 4 | omitted | no (occasionally `##io=4`) |
| HISAT2 / Bowtie2 / Salmon (RNA-seq scale) | 4-10 | omitted | no |
| BWA on exome/genome splits | 16 | 20 | yes, e.g. `6x<path>` |
| deepTools heatmap/matrix ops | 4 | 20-30 | no |
| Picard MarkDuplicates | omitted-1 | ~19 | sometimes |
| GATK BaseRecalibrator (per-region) | 1-2 | 14-16 | yes, `##io=4` too |
| GATK HaplotypeCaller (per-region) | 1 | 14 | yes, `Nx<file>` |
| GATK GenotypeGVCFs / VariantRecalibrator | omitted | 16 | sometimes, flat GB |

These are starting points from real, working scripts — not hard rules.
Adjust for the actual data scale of the task at hand (whole-genome vs
targeted panel, cohort size, etc.).

## `##local=` spec forms

- Plain integer: flat GB reservation, e.g. `##local=16`.
- `Nx<file>`: `N` times the size of the referenced (templated) file, e.g.
  `##local=4x<sample>/<sample>.bam` — use when local-disk need scales with
  a specific input rather than being roughly fixed.
- A literal file path (no `Nx` prefix): uses that file's own size in GB.
- A comma list of paths: sums their sizes.

Pair `##local=`/`<local>` staging with `rmscp`/`rmssync` (flock-guarded
`cp`/`rsync`) to move files into and out of `$RMS_STEP_LOCAL_DIR` safely
even when multiple concurrent commands on the same worker might race on a
shared file. See `idioms.md` for the exact call pattern.
