"""Field validation, content construction, and saved-value comparisons."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from changes import (build_changes, validate_fields, validate_spec, validate_transition_fields,
                     validate_transition_spec, value_matches)


class ChangeTests(unittest.TestCase):
    def test_markdown_is_built_as_adf_for_a_textarea(self):
        spec = {"text": {"customfield_10010": {"markdown": "**Required**"}}}
        metadata = {"customfield_10010": {"schema": {
            "type": "string", "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea"}}}

        fields, operations = build_changes(spec, metadata, {})

        self.assertEqual(fields, {"customfield_10010": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "Required", "marks": [{"type": "strong"}]}
            ]}
        ]}})
        self.assertEqual(operations, {})

    def test_plain_custom_field_remains_a_string(self):
        spec = {"text": {"customfield_10010": {"text": "Literal **criteria**"}}}
        metadata = {"customfield_10010": {"schema": {
            "type": "string", "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield"}}}

        fields, operations = build_changes(spec, metadata, {})

        self.assertEqual(fields, {"customfield_10010": "Literal **criteria**"})
        self.assertEqual(operations, {})

    def test_plain_custom_field_does_not_accept_an_adf_writer(self):
        spec = {"text": {"customfield_10010": {"markdown": "**Criteria**"}}}
        metadata = {"customfield_10010": {"schema": {"type": "string"}}}

        with self.assertRaisesRegex(ValueError, "does not support that text format"):
            build_changes(spec, metadata, {})

    def test_unknown_custom_field_type_is_not_guessed(self):
        spec = {"text": {"customfield_10010": {"markdown": "Criteria"}}}

        with self.assertRaisesRegex(ValueError, "not available"):
            build_changes(spec, {}, {})

    def test_description_cannot_be_sent_as_markdown_in_raw_fields(self):
        fields = {"description": "## Not ADF"}
        metadata = {"description": {"operations": ["set"], "schema": {"type": "string"}}}

        with self.assertRaisesRegex(ValueError, "version 1 document"):
            validate_fields(fields, metadata)

    def test_required_field_cannot_be_cleared(self):
        metadata = {"summary": {"operations": ["set"], "required": True, "schema": {"type": "string"}}}

        with self.assertRaisesRegex(ValueError, "cannot be cleared"):
            validate_fields({"summary": None}, metadata)

    def test_optional_field_can_be_explicitly_cleared(self):
        metadata = {"description": {"operations": ["set"], "schema": {"type": "string"}}}

        result = validate_fields({"description": None}, metadata)

        self.assertIsNone(result)

    def test_required_create_field_with_default_can_be_omitted(self):
        metadata = {"priority": {"required": True, "hasDefaultValue": True, "operations": ["set"]}}

        result = validate_fields({}, metadata, creating=True)

        self.assertIsNone(result)

    def test_option_must_be_in_available_metadata_choices(self):
        metadata = {"priority": {"operations": ["set"], "schema": {"type": "priority"},
                                  "allowedValues": [{"id": "1", "name": "High"}]}}

        with self.assertRaisesRegex(ValueError, "not listed"):
            validate_fields({"priority": {"id": "999"}}, metadata)

    def test_reference_requires_an_explicit_identifier(self):
        metadata = {"assignee": {"operations": ["set"], "schema": {"type": "user"}}}

        with self.assertRaisesRegex(ValueError, "explicit identifier"):
            validate_fields({"assignee": {}}, metadata)

    def test_boolean_is_not_accepted_as_a_number(self):
        metadata = {"customfield_10010": {"operations": ["set"], "schema": {"type": "number"}}}

        with self.assertRaisesRegex(ValueError, "finite number"):
            validate_fields({"customfield_10010": True}, metadata)

    def test_non_finite_number_is_rejected(self):
        metadata = {"customfield_10010": {"operations": ["set"], "schema": {"type": "number"}}}

        with self.assertRaisesRegex(ValueError, "finite number"):
            validate_fields({"customfield_10010": float("inf")}, metadata)

    def test_string_array_cannot_contain_objects(self):
        metadata = {"customfield_10010": {"operations": ["set"], "schema": {"type": "array", "items": "string"}}}

        with self.assertRaisesRegex(ValueError, "array of strings"):
            validate_fields({"customfield_10010": [{"id": "1"}]}, metadata)

    def test_duplicate_label_operations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            validate_spec({"labels": {"add": ["same", "same"]}}, creating=False)

    def test_opposing_label_operations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "same label"):
            validate_spec({"labels": {"add": ["same"], "remove": ["same"]}}, creating=False)

    def test_label_replacement_cannot_be_combined_with_operations(self):
        with self.assertRaisesRegex(ValueError, "label operations"):
            validate_spec({"fields": {"labels": []}, "labels": {"add": ["new"]}}, creating=False)

    def test_label_operations_skip_values_that_already_match(self):
        spec = {"labels": {"add": ["keep"], "remove": ["absent"]}}

        fields, operations = build_changes(spec, {}, {"labels": ["keep"]})

        self.assertEqual(fields, {})
        self.assertEqual(operations, {})

    def test_reference_comparison_allows_server_metadata(self):
        result = value_matches({"accountId": "user-1"},
                               {"accountId": "user-1", "displayName": "Example"}, "assignee")

        self.assertTrue(result)

    def test_custom_json_comparison_does_not_ignore_removed_properties(self):
        result = value_matches({"keep": "value"}, {"keep": "value", "remove": "old"},
                               "customfield_10010", schema={"type": "any"})

        self.assertFalse(result)

    def test_empty_custom_object_is_not_a_wildcard(self):
        result = value_matches({}, {"old": "value"}, "customfield_10010", schema={"type": "any"})

        self.assertFalse(result)

    def test_custom_option_reference_allows_extra_metadata(self):
        result = value_matches({"id": "1"}, {"id": "1", "value": "Red"},
                               "customfield_10010", schema={"type": "option"})

        self.assertTrue(result)

    def test_option_array_order_does_not_change_its_meaning(self):
        result = value_matches([{"id": "1"}, {"id": "2"}],
                               [{"id": "2", "value": "Blue"}, {"id": "1", "value": "Red"}],
                               "customfield_10010", schema={"type": "array", "items": "option"})

        self.assertTrue(result)

    def test_equal_integer_and_float_values_verify(self):
        result = value_matches(5, 5.0, "customfield_10010")

        self.assertTrue(result)

    def test_boolean_does_not_verify_as_a_number(self):
        result = value_matches(True, 1, "customfield_10010")

        self.assertFalse(result)

    def test_malformed_saved_labels_fail_verification_without_a_type_error(self):
        result = value_matches(["keep", "new"], ["keep", 1], "labels")

        self.assertFalse(result)

    def test_adf_verification_ignores_generated_local_ids_only(self):
        expected = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Same content"}]}]}
        actual = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "attrs": {"localId": "generated"},
             "content": [{"type": "text", "text": "Same content"}]}]}

        result = value_matches(expected, actual, "description")

        self.assertTrue(result)

    def test_transition_accepts_no_screen_fields_and_rejects_other_input(self):
        self.assertEqual(validate_transition_spec({}), [])
        with self.assertRaisesRegex(ValueError, "Unknown input keys"):
            validate_transition_spec({"update": {"comment": []}})

    def test_transition_rejects_protected_fields_and_operations(self):
        with self.assertRaisesRegex(ValueError, "not supported"):
            validate_transition_spec({"fields": {"status": {"id": "2"}}})
        with self.assertRaisesRegex(ValueError, "not supported"):
            validate_transition_spec({"fields": {"worklog": {"timeSpent": "1h"}}})
        with self.assertRaisesRegex(ValueError, "Unknown input keys"):
            validate_transition_spec({"labels": {"add": ["new"]}})
        with self.assertRaisesRegex(ValueError, "Unknown input keys"):
            validate_transition_spec({"sections": []})

    def test_resolution_requires_a_listed_numeric_id_only(self):
        metadata = {"resolution": {"required": True, "operations": ["set"],
                                   "schema": {"type": "resolution"},
                                   "allowedValues": [{"id": "10000", "name": "Done"}]}}

        validate_transition_fields({"resolution": {"id": "10000"}}, metadata, {"resolution": None})
        with self.assertRaisesRegex(ValueError, "ID offered"):
            validate_transition_fields({"resolution": {"name": "Done"}}, metadata, {"resolution": None})
        with self.assertRaisesRegex(ValueError, "ID offered"):
            validate_transition_fields({"resolution": {"id": "999"}}, metadata, {"resolution": None})
        with self.assertRaisesRegex(ValueError, "ID offered"):
            validate_transition_fields({"resolution": {"id": "10000", "name": "Done"}},
                                       metadata, {"resolution": None})

    def test_resolution_without_offered_choices_is_not_guessed(self):
        metadata = {"resolution": {"required": False, "operations": ["set"],
                                   "schema": {"type": "resolution"}}}

        with self.assertRaisesRegex(ValueError, "ID offered"):
            validate_transition_fields({"resolution": {"id": "10000"}}, metadata, {})

    def test_transition_requires_missing_screen_value_but_accepts_existing_or_default(self):
        metadata = {"customfield_1": {"required": True, "operations": ["set"],
                                       "schema": {"type": "string"}}}

        with self.assertRaisesRegex(ValueError, "Missing required transition field"):
            validate_transition_fields({}, metadata, {"customfield_1": None})
        with self.assertRaisesRegex(ValueError, "Missing required transition field"):
            validate_transition_fields({}, metadata, {})
        validate_transition_fields({}, metadata, {"customfield_1": "existing"})
        validate_transition_fields({}, {"customfield_1": {**metadata["customfield_1"],
                                                          "hasDefaultValue": True}}, {})

    def test_transition_rejects_required_special_operation(self):
        metadata = {"comment": {"required": True, "operations": ["add"],
                                "schema": {"type": "array"}}}

        with self.assertRaisesRegex(ValueError, "unsupported operation"):
            validate_transition_fields({}, metadata, {})

    def test_ordinary_update_cannot_set_resolution(self):
        with self.assertRaisesRegex(ValueError, "not supported"):
            validate_spec({"fields": {"resolution": {"id": "10000"}}}, creating=False)

    def test_adf_verification_does_not_ignore_different_content(self):
        expected = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Expected"}]}]}
        actual = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Other"}]}]}

        result = value_matches(expected, actual, "description")

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
