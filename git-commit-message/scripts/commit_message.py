#!/usr/bin/env python3
"""Check commit style or validate message formatting.

Use check_style or validate_format [file|-]. Validation reads stdin by default.
Exit 0 for success, 1 for format errors, or 2 for input or Git errors.
"""

import argparse
import re
import subprocess
import sys
from enum import Enum
from pathlib import Path

MAX_SUBJECT_LENGTH = 50
MAX_BODY_LINE_LENGTH = 72
HISTORY_LIMIT = 30
MIN_HISTORY = 10
STYLE_THRESHOLD = 80
# Count known types here
CONVENTIONAL_SUBJECT = re.compile(
    r"(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\([^()\r\n]+\))?!?: \S",
    re.IGNORECASE,
)
COMPONENT_SUBJECT = re.compile(r"[\w./@+-]+: \S")


class Style(Enum):
    PLAIN = "plain"
    CONVENTIONAL = "conventional"
    COMPONENT = "component"


def check_style(repo: str | Path = ".") -> Style:
    """Require at least 80% of 10-30 non-merge subjects for a non-plain style."""
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=repo, capture_output=True, encoding="utf-8",
    )
    if head.returncode == 1 and not head.stderr:
        return Style.PLAIN  # An unborn branch has no history.
    head.check_returncode()
    history = subprocess.run(
        ["git", "log", f"-{HISTORY_LIMIT}", "--no-merges", "--format=%s"],
        cwd=repo, capture_output=True, encoding="utf-8", check=True,
    )
    subjects = history.stdout.splitlines()
    if len(subjects) < MIN_HISTORY:
        return Style.PLAIN
    matches = {Style.CONVENTIONAL: 0, Style.COMPONENT: 0}
    for subject in subjects:
        if CONVENTIONAL_SUBJECT.match(subject):
            matches[Style.CONVENTIONAL] += 1
        elif COMPONENT_SUBJECT.match(subject):
            matches[Style.COMPONENT] += 1
    for style, count in matches.items():
        if count * 100 >= len(subjects) * STYLE_THRESHOLD:
            return style
    return Style.PLAIN


def validate_format(message: str) -> list[str]:
    """Return formatting errors for a commit message."""
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


def main(argv: list[str] | None = None) -> int:
    """Run the selected check."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check_style", help="check recent non-merge subjects")
    validation = commands.add_parser("validate_format", help="check formatting")
    validation.add_argument(
        "message_file", nargs="?", type=Path,
        help="commit message file; omit or use '-' to read standard input",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "check_style":
            print(check_style().value)
            return 0
        message = (
            sys.stdin.read()
            if args.message_file is None or args.message_file == Path("-")
            else args.message_file.read_text(encoding="utf-8")
        )
    except subprocess.CalledProcessError as error:
        print((error.stderr or str(error)).strip(), file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as error:
        print(f"cannot run {args.command}: {error}", file=sys.stderr)
        return 2

    errors = validate_format(message)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
