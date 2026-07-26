#!/usr/bin/env python3
"""Validate the layout and line lengths of a Git commit message.

Read the message from a file or, when no file or `-` is given, from standard
input. Exit with status 1 and print all validation errors when the message is
invalid.
"""

import argparse
import sys
from pathlib import Path

MAX_SUBJECT_LENGTH = 50
MAX_BODY_LINE_LENGTH = 72


def validate(message: str) -> list[str]:
    """Return validation errors for a commit message."""
    lines = message.splitlines()
    errors: list[str] = []

    subject = lines[0] if lines else ""
    if not subject.strip():
        errors.append("subject must not be empty")

    if len(subject) > MAX_SUBJECT_LENGTH:
        errors.append(
            f"subject is {len(subject)} characters; "
            f"maximum is {MAX_SUBJECT_LENGTH}"
        )
    if subject.rstrip().endswith("."):
        errors.append("subject must not end with a period")

    if len(lines) > 1 and lines[1]:
        errors.append("line 2 must be blank to separate subject from body")

    for line_number, line in enumerate(lines[1:], start=2):
        if len(line) > MAX_BODY_LINE_LENGTH:
            errors.append(
                f"body line {line_number} is {len(line)} characters; "
                f"maximum is {MAX_BODY_LINE_LENGTH}"
            )

    return errors


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "message_file",
        nargs="?",
        type=Path,
        help="commit message file; omit or use '-' to read standard input",
    )
    return parser.parse_args()


def main() -> int:
    """Run the command-line validator."""
    args = parse_args()
    try:
        message = (
            sys.stdin.read()
            if args.message_file is None or args.message_file == Path("-")
            else args.message_file.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError) as error:
        print(f"cannot read commit message: {error}", file=sys.stderr)
        return 2

    errors = validate(message)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
