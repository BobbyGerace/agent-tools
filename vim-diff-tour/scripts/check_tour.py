#!/usr/bin/env python3
"""Validate a vim-diff-tour JSON file before handing it to the user.

Checks that every entry resolves to a real location and that the text fits on
one quickfix line. Exits non-zero if anything is wrong.

    python3 check_tour.py /tmp/diff-tour.json --root .
"""

import argparse
import json
import sys
from pathlib import Path

TEXT_TARGET = 55
TEXT_MAX = 70
MAX_ITEMS = 12


def literal_from_pattern(pattern):
    """Return the literal string a `\\V`-prefixed pattern searches for.

    Only \\V patterns can be checked reliably -- under very-nomagic everything
    except backslash is literal. Anything else is left to Vim.
    """
    if not pattern.startswith("\\V"):
        return None
    body = pattern[2:]
    if "\\" in body:
        return None
    return body


def check(path, root):
    problems = []
    notes = []

    try:
        data = json.loads(Path(path).read_text())
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"], []

    if not isinstance(data, dict) or "items" not in data:
        return ['top level must be an object with "title" and "items"'], []

    if not data.get("title"):
        problems.append('missing "title" -- the quickfix window will be unlabelled')

    items = data["items"]
    if not isinstance(items, list) or not items:
        return ['"items" must be a non-empty list'], []

    stops = [i for i in items if i.get("filename")]
    headers = [i for i in items if not i.get("filename")]

    if len(stops) > MAX_ITEMS:
        notes.append(
            f"{len(stops)} stops -- past {MAX_ITEMS} the tour stops feeling curated"
        )
    if headers and len(stops) < 6:
        notes.append("chapter headers on a short tour may be more scaffolding than help")

    for n, item in enumerate(items):
        tag = f"item {n}"
        text = item.get("text", "")

        if not text.strip():
            problems.append(f"{tag}: empty text")
        elif len(text) > TEXT_MAX:
            problems.append(f"{tag}: text is {len(text)} chars (max {TEXT_MAX}): {text!r}")
        elif len(text) > TEXT_TARGET:
            notes.append(f"{tag}: text is {len(text)} chars (target {TEXT_TARGET})")

        for field in ("type", "nr", "col"):
            if field in item:
                notes.append(f"{tag}: drop \"{field}\" -- it adds a column of noise")

        filename = item.get("filename")
        if not filename:
            continue  # chapter header

        fpath = Path(root) / filename
        if not fpath.is_file():
            problems.append(f"{tag}: no such file: {filename}")
            continue

        try:
            lines = fpath.read_text(errors="replace").splitlines()
        except OSError as e:
            problems.append(f"{tag}: cannot read {filename}: {e}")
            continue

        has_pattern = "pattern" in item
        has_lnum = "lnum" in item

        if not has_pattern and not has_lnum:
            problems.append(f"{tag}: needs a pattern or an lnum")
        if has_pattern and has_lnum:
            notes.append(f"{tag}: has both pattern and lnum -- Vim uses the pattern")

        if has_pattern:
            pattern = item["pattern"]
            if not pattern.startswith("\\V"):
                notes.append(f"{tag}: pattern lacks a \\V prefix, so it is not literal")
            literal = literal_from_pattern(pattern)
            if literal is None:
                notes.append(f"{tag}: pattern not statically checkable: {pattern!r}")
            else:
                hits = sum(1 for line in lines if literal in line)
                if hits == 0:
                    problems.append(f"{tag}: pattern matches nothing in {filename}: {literal!r}")
                elif hits > 1:
                    problems.append(
                        f"{tag}: pattern matches {hits} lines in {filename} -- "
                        f"anchor is not distinctive: {literal!r}"
                    )
        elif has_lnum:
            lnum = item["lnum"]
            if not isinstance(lnum, int) or lnum < 1 or lnum > len(lines):
                problems.append(
                    f"{tag}: lnum {lnum} out of range for {filename} ({len(lines)} lines)"
                )

    return problems, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tour", help="path to the tour JSON file")
    ap.add_argument("--root", default=".", help="repo root the filenames are relative to")
    args = ap.parse_args()

    problems, notes = check(args.tour, args.root)

    for note in notes:
        print(f"note:    {note}")
    for problem in problems:
        print(f"PROBLEM: {problem}")

    if problems:
        print(f"\n{len(problems)} problem(s) -- fix before delivering the tour")
        return 1
    print(f"\ntour OK{f' ({len(notes)} note(s))' if notes else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
