"""Test commit style and formatting without changing Git state."""

import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from commit_message import Style, check_style, main, validate_format


class StyleTests(unittest.TestCase):
    def setUp(self):
        git = patch("commit_message.subprocess.run")
        self.git = git.start()
        self.addCleanup(git.stop)
        self.git.return_value = subprocess.CompletedProcess(
            ["git"], 0, stdout="", stderr=""
        )

    def test_empty_history_is_plain(self):
        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_nine_conventional_subjects_are_not_enough(self):
        self.git.return_value.stdout = "feat: Add config\n" * 9

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_eight_of_ten_subjects_are_enough(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 8 + "Update docs\n" * 2
        )

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_seven_of_ten_subjects_are_not_enough(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 7 + "Update docs\n" * 3
        )

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_twenty_four_of_thirty_subjects_are_enough(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 24 + "Update docs\n" * 6
        )

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_twenty_three_of_thirty_subjects_are_not_enough(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 23 + "Update docs\n" * 7
        )

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_scopes_are_recognized(self):
        self.git.return_value.stdout = "fix(parser): Handle empty input\n" * 10

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_breaking_markers_are_recognized(self):
        self.git.return_value.stdout = "feat!: Remove old config\n" * 10

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_scopes_with_breaking_markers_are_recognized(self):
        self.git.return_value.stdout = "feat(core)!: Remove old config\n" * 10

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_types_are_case_insensitive(self):
        self.git.return_value.stdout = "Feat: Add config\n" * 10

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_other_known_types_are_recognized(self):
        self.git.return_value.stdout = (
            "docs: Add guide\nstyle: Format parser\n"
            "refactor: Split parser\nperf: Reduce allocations\n"
            "test: Cover empty input\nbuild: Update compiler\n"
            "ci: Run checks\nchore: Update dependencies\n"
            "Update docs\nUpdate config\n"
        )

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_revert_type_is_recognized(self):
        self.git.return_value.stdout = "revert: Undo change\n" * 10

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_empty_descriptions_are_not_conventional(self):
        self.git.return_value.stdout = "fix: \n" * 10

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_empty_subjects_count_against_the_threshold(self):
        self.git.return_value.stdout = "fix: Handle empty input\n" * 23 + "\n" * 7

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_component_prefixes_are_recognized(self):
        self.git.return_value.stdout = "subdir: Update config\n" * 30

        result = check_style()

        self.assertIs(result, Style.COMPONENT)

    def test_empty_scopes_are_not_conventional(self):
        self.git.return_value.stdout = "feat(): Add config\n" * 30

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_unborn_branch_is_plain(self):
        self.git.return_value.returncode = 1

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_git_errors_are_not_reported_as_plain_style(self):
        self.git.return_value.returncode = 128
        self.git.return_value.stderr = "fatal: not a git repository"

        with self.assertRaises(subprocess.CalledProcessError):
            check_style()

    def test_style_command_prints_only_the_style(self):
        self.git.return_value.stdout = "feat: Add config\n" * 10
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = main(["check_style"])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "conventional\n")

    def test_style_command_reports_git_errors(self):
        self.git.return_value.returncode = 128
        self.git.return_value.stderr = "fatal: not a git repository"
        output = io.StringIO()

        with patch("sys.stderr", output):
            result = main(["check_style"])

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "fatal: not a git repository\n")

    def test_nine_component_subjects_are_not_enough(self):
        self.git.return_value.stdout = "subdir: Update config\n" * 9

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_eight_of_ten_component_subjects_are_enough(self):
        self.git.return_value.stdout = (
            "subdir: Update config\n" * 8 + "Update docs\n" * 2
        )

        result = check_style()

        self.assertIs(result, Style.COMPONENT)

    def test_seven_of_ten_component_subjects_are_not_enough(self):
        self.git.return_value.stdout = (
            "subdir: Update config\n" * 7 + "Update docs\n" * 3
        )

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_component_names_can_differ(self):
        self.git.return_value.stdout = (
            "git-commit-message: Check style\nAPI: Handle empty input\n"
            "src/parser: Fix lookup\n@app/core: Update config\n"
        ) * 2 + "Update docs\nUpdate config\n"

        result = check_style()

        self.assertIs(result, Style.COMPONENT)

    def test_conventional_subjects_do_not_count_as_component_evidence(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 7 + "subdir: Update config\n" * 3
        )

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_conventional_majority_is_not_component_style(self):
        self.git.return_value.stdout = (
            "fix: Handle empty input\n" * 8 + "subdir: Update config\n" * 2
        )

        result = check_style()

        self.assertIs(result, Style.CONVENTIONAL)

    def test_component_majority_is_not_conventional_style(self):
        self.git.return_value.stdout = (
            "subdir: Update config\n" * 8 + "fix: Handle empty input\n" * 2
        )

        result = check_style()

        self.assertIs(result, Style.COMPONENT)

    def test_empty_component_descriptions_are_not_evidence(self):
        self.git.return_value.stdout = "subdir: \n" * 10

        result = check_style()

        self.assertIs(result, Style.PLAIN)

    def test_style_command_prints_the_component_value(self):
        self.git.return_value.stdout = "subdir: Update config\n" * 10
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = main(["check_style"])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "component\n")

    def test_style_command_prints_the_plain_value(self):
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = main(["check_style"])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "plain\n")


class FormatTests(unittest.TestCase):
    def test_subject_only_message_is_valid(self):
        result = validate_format("Fix empty input\n")

        self.assertEqual(result, [])

    def test_exact_line_limits_are_valid(self):
        message = "A" * 50 + "\n\n" + "b" * 72

        result = validate_format(message)

        self.assertEqual(result, [])

    def test_empty_message_is_invalid(self):
        result = validate_format("")

        self.assertEqual(result, ["subject must not be empty"])

    def test_whitespace_subject_is_invalid(self):
        result = validate_format("  ")

        self.assertEqual(result, ["subject must not be empty"])

    def test_all_format_errors_are_returned(self):
        message = "A" * 50 + ".\n" + "b" * 73

        result = validate_format(message)

        self.assertEqual(result, [
            "subject is 51 characters; maximum is 50",
            "subject must not end with a period",
            "line 2 must be blank to separate subject from body",
            "body line 2 is 73 characters; maximum is 72",
        ])

    def test_validation_command_reads_stdin(self):
        message = io.StringIO("Fix empty input\n")

        with patch("sys.stdin", message):
            result = main(["validate_format"])

        self.assertEqual(result, 0)

    def test_dash_selects_stdin(self):
        message = io.StringIO("Fix empty input\n")

        with patch("sys.stdin", message):
            result = main(["validate_format", "-"])

        self.assertEqual(result, 0)

    def test_validation_command_reads_a_file(self):
        with patch.object(Path, "read_text", return_value="Fix empty input\n"):
            result = main(["validate_format", "draft.txt"])

        self.assertEqual(result, 0)

    def test_validation_command_reports_errors(self):
        message = io.StringIO("Fix empty input.\n")
        output = io.StringIO()

        with patch("sys.stdin", message), patch("sys.stderr", output):
            result = main(["validate_format"])

        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "subject must not end with a period\n")

    def test_validation_command_reports_input_errors(self):
        output = io.StringIO()

        with patch.object(Path, "read_text", side_effect=OSError("missing file")):
            with patch("sys.stderr", output):
                result = main(["validate_format", "draft.txt"])

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "cannot run validate_format: missing file\n")


if __name__ == "__main__":
    unittest.main()
