#!/usr/bin/env python3
"""
Static linter for .rms pipeline scripts, mirroring the actual RMS parser's
rules (see ../references/grammar.md and ../references/engine_quirks.md).

This is NOT a substitute for a real `rms -t` compile check -- it catches a
different class of problem: things the real parser would accept fine but
that are known gotchas on this engine build (silently-unresolved template
variables, inert directives, forward ##after references), plus a few
structural checks that mirror the parser's own fatal-error conditions.

Usage:
    python3 validate_rms.py path/to/script.rms
"""
import re
import sys

KNOWN_SETUP_DIRECTIVES = {
    "lang", "bash", "perl", "python", "r", "sheet", "option", "argv",
    "vol", "redo", "outline", "errline", "totalio",
}
KNOWN_STEP_OPTIONS = {
    "bash", "perl", "python", "r", "ppn", "mem", "io", "outline",
    "errline", "boxer", "docker", "vol", "local", "tmp", "after", "redo",
}
INERT_DIRECTIVES = {"redo", "docker", "boxer", "vol", "qc"}
CMD_LOOKUP_TOKENS = {"tmp", "perm", "local", "ppn"}

TOKEN_RE = re.compile(r"<(\w+)[,>]")
GENERIC_VAR_RE = re.compile(r"##(\w+)=\(\s*(.+?)\s*\)\s*$")
BARE_KV_RE = re.compile(r"##(\w+)=(.+)$")


def die(msg):
    print("ERROR: " + msg)


def warn(msg):
    print("WARNING: " + msg)


def parse_sheet_header(sheet_lines):
    """Best-effort mimic of the engine's delimiter auto-detect on the first
    line of an embedded ##sheet block (or a ##argv= usage string, which the
    engine treats as a header line the same way -- see the ##argv handling
    below), returning lowercased column names, or [] if nothing usable was
    found.

    The real engine detects the delimiter from whatever non-word character
    follows the header's first run of word-characters -- but it always has
    one, because it appends a trailing "\\n" before parsing. A single-word
    header string with no trailing newline (e.g. this function called
    directly on "sample") has no such character, so that case is handled
    separately below rather than mis-reported as "no columns found."
    """
    if not sheet_lines:
        return []
    first = sheet_lines[0].rstrip("\n")
    if not first:
        return []
    m = re.match(r"(\w+)([^\w])", first)
    if m:
        delim = m.group(2)
        if delim == "\t":
            cols = first.split("\t")
        elif delim == ",":
            cols = first.split(",")
        else:
            cols = first.split()
    elif re.match(r"^\w+$", first):
        # Single word, no delimiter character present at all -- one column.
        cols = [first]
    else:
        return []
    return [c.strip().lower() for c in cols if c.strip()]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]

    with open(path, "rb") as fh:
        raw = fh.read()
    size = len(raw)

    errors = []
    warnings = []

    if size > 1_000_000:
        errors.append(
            "File is %d bytes -- exceeds RMS's 1,000,000 byte hard limit "
            "for .rms scripts. The engine will reject this outright." % size
        )

    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")

    declared_columns = set()
    pipeline_vars = set()
    step_names = []          # in file order
    step_names_seen = set()
    in_sheet_block = False
    sheet_marker = None
    sheet_buffer = []
    argv_seen = False
    setup_has_script_body = False

    # phase moves strictly forward: setup -> env -> init -> step
    # (env/init are each optional and skippable)
    phase = "setup"

    current_step_name = None
    current_step_namedvalues = set()  # keys from ##KEY=... if COL=VAL, this step only
    pending_checkfile = None  # (lineno, stepname, checkfile_text) -- checked once
                               # that step's body (and its 'if col=val' lookups)
                               # has been fully seen, since checkFile is templated
                               # too but appears before the body that defines them

    def check_tokens(text, lineno, stepname, namedvalues):
        for m in TOKEN_RE.finditer(text):
            name = m.group(1).lower()
            if (
                name not in declared_columns
                and name not in pipeline_vars
                and name not in CMD_LOOKUP_TOKENS
                and name not in namedvalues
            ):
                warnings.append(
                    "line %d: step %r references <%s>, which isn't "
                    "resolvable against any declared manifest column, "
                    "pipeline variable, cmd-lookup token (tmp/perm/local/"
                    "ppn), or this step's own 'if col=val' lookup. If "
                    "unresolved at runtime, RMS leaves it as literal text "
                    "-- NOT an error -- which usually breaks the "
                    "generated shell command in a confusing way. If this "
                    "column is produced by a dynamic setup-script sheet "
                    "this linter can't see, it's a false positive; "
                    "otherwise, check spelling." % (lineno, stepname, name)
                )

    for i, raw_line in enumerate(lines):
        lineno = i + 1
        line = raw_line.rstrip("\r")

        if in_sheet_block:
            if line.startswith(sheet_marker):
                declared_columns.update(parse_sheet_header(sheet_buffer))
                in_sheet_block = False
                sheet_buffer = []
            else:
                sheet_buffer.append(line)
            continue

        stripped = line.strip()
        if stripped == "":
            continue
        # bash-style '#'-comment or '## '-comment: literal passthrough, never a directive
        is_comment_only = (line.startswith("#") and not line.startswith("##")) or line.startswith("## ")

        if line.startswith("#### "):
            if pending_checkfile is not None:
                pc_lineno, pc_name, pc_text = pending_checkfile
                check_tokens(pc_text, pc_lineno, pc_name, current_step_namedvalues)
                pending_checkfile = None

            fields = stripped.split()
            if len(fields) != 4:
                errors.append(
                    "line %d: step header must have exactly 4 fields "
                    "'#### name grouping checkFile', found %d: %r"
                    % (lineno, len(fields), stripped)
                )
            else:
                name = fields[1]
                grouping = fields[2].lower().split(",")
                pending_checkfile = (lineno, name, fields[3])
                if name in step_names_seen:
                    errors.append(
                        "line %d: duplicate step name %r -- step names must "
                        "be unique" % (lineno, name)
                    )
                step_names_seen.add(name)
                step_names.append(name)
                current_step_name = name
                current_step_namedvalues = set()
                if grouping != ["all"]:
                    for g in grouping:
                        if (
                            g not in declared_columns
                            and g not in pipeline_vars
                        ):
                            warnings.append(
                                "line %d: step %r groups by column %r, which "
                                "isn't among the columns/variables this "
                                "linter could statically detect (%s). If it "
                                "comes from a dynamic setup-script sheet, "
                                "this is a false positive -- otherwise "
                                "double check the column name." % (
                                    lineno, name, g,
                                    ", ".join(sorted(declared_columns | pipeline_vars)) or "none found",
                                )
                            )
            phase = "step"
            continue

        if not is_comment_only and line.startswith("##"):
            key_match = re.match(r"##(\w+)", line)
            key = key_match.group(1).lower() if key_match else ""

            if phase == "setup":
                if key == "sheet":
                    m = re.match(r"##sheet=(\w+)", line)
                    if m:
                        in_sheet_block = True
                        sheet_marker = m.group(1)
                        sheet_buffer = []
                    continue
                if key == "argv":
                    argv_seen = True
                    # The engine uses the text after '##argv=' VERBATIM as
                    # the synthetic manifest's header line (parsePipeline.py:
                    # newsheet.append(pipeline.setupArgvHeader + "\n")),
                    # parsed by the same delimiter-auto-detect rule as any
                    # other sheet header -- so we can resolve real column
                    # name(s) here instead of blanket-suppressing checks.
                    m = re.match(r"##argv=(.*)$", stripped)
                    if m:
                        declared_columns.update(parse_sheet_header([m.group(1)]))
                    continue
                if key == "env":
                    phase = "env"
                    continue
                if key == "init":
                    phase = "init"
                    continue
                if key not in KNOWN_SETUP_DIRECTIVES:
                    gm = GENERIC_VAR_RE.match(line)
                    if gm:
                        pipeline_vars.add(gm.group(1).lower())
                    else:
                        bm = BARE_KV_RE.match(stripped)
                        if bm:
                            errors.append(
                                "line %d: %r looks like a pipeline-variable "
                                "directive but its value isn't parenthesized "
                                "-- RMS requires ##name=(value1 value2 ...). "
                                "A bare '##name=column' form (as sometimes "
                                "shown in the docs) is a FATAL parse error on "
                                "this engine build, not a valid directive."
                                % (lineno, stripped)
                            )
                        else:
                            errors.append(
                                "line %d: unrecognized setup-header directive "
                                "%r" % (lineno, stripped)
                            )
                elif key in INERT_DIRECTIVES:
                    warnings.append(
                        "line %d: %r is parsed but functionally inert on "
                        "this engine build (see engine_quirks.md) -- don't "
                        "promise this behavior to a user." % (lineno, stripped)
                    )
                continue

            if phase in ("env", "init"):
                if key == "init":
                    phase = "init"
                    continue
                # Directive lines inside ##env/##init blocks (e.g. ##local=
                # in the env header) aren't strictly validated here -- low
                # value, higher false-positive risk. Just pass through.
                continue

            # phase == "step": step-body option line
            if " if " in line:
                m = re.match(r"##(\w+)=(\w+)\s+if\s+(\w+)=(\w+)", stripped)
                if m:
                    current_step_namedvalues.add(m.group(1).lower())
                continue
            if key == "after":
                afterval = line.split("=", 1)[1] if "=" in line else ""
                names = [n.strip() for n in afterval.split(",") if n.strip()]
                for n in names:
                    if n not in step_names_seen:
                        errors.append(
                            "line %d: step %r has ##after=%r referencing "
                            "step %r, which hasn't been defined yet (or "
                            "doesn't exist) -- forward references are a "
                            "fatal error; ##after can only name steps "
                            "already defined earlier in the file."
                            % (lineno, current_step_name, afterval, n)
                        )
                continue
            if key == "qc" or stripped.startswith("##qc"):
                errors.append(
                    "line %d: '##qc' is not reachable syntax on this "
                    "engine build -- its parser entry point is disabled. "
                    "This will be treated as an unrecognized step option "
                    "and fail to parse." % lineno
                )
                continue
            if key not in KNOWN_STEP_OPTIONS:
                errors.append(
                    "line %d: unrecognized step option %r -- RMS will "
                    "treat this as a fatal parse error unless it's a "
                    "'##key=value if col=val' conditional form."
                    % (lineno, stripped)
                )
            elif key in INERT_DIRECTIVES:
                warnings.append(
                    "line %d: %r is parsed but functionally inert on "
                    "this engine build (see engine_quirks.md) -- don't "
                    "promise this behavior to a user." % (lineno, stripped)
                )
            continue

        # literal line: setup-script body, env/init injected code, or step script body
        if phase == "setup":
            if not is_comment_only:
                setup_has_script_body = True
        elif phase == "step":
            check_tokens(line, lineno, current_step_name, current_step_namedvalues)
        # phase in ("env", "init"): literal injected code, not scanned

    if pending_checkfile is not None:
        pc_lineno, pc_name, pc_text = pending_checkfile
        check_tokens(pc_text, pc_lineno, pc_name, current_step_namedvalues)

    if setup_has_script_body and argv_seen:
        errors.append(
            "Setup header appears to contain both non-comment script body "
            "lines AND '##argv=' -- these are mutually exclusive; the "
            "engine fatal-errors on this combination."
        )

    print("=== validate_rms.py: %s ===" % path)
    print("Declared manifest columns (best-effort, static analysis only): %s"
          % (", ".join(sorted(declared_columns)) or "(none detected statically)"))
    print("Declared pipeline variables: %s"
          % (", ".join(sorted(pipeline_vars)) or "(none)"))
    print("Steps found, in order: %s" % (", ".join(step_names) or "(none)"))
    print()

    if not errors and not warnings:
        print("No issues found by static analysis.")
    for e in errors:
        die(e)
    for w in warnings:
        warn(w)

    print()
    print("%d error(s), %d warning(s)." % (len(errors), len(warnings)))
    print(
        "Static analysis only -- this does NOT replace a real 'rms -t' "
        "compile check with an actual manifest. See cli_and_environment.md."
    )
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
