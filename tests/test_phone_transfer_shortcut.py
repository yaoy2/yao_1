"""Check the generated Shortcut's data flow, without claiming iOS runtime QA."""

import importlib.util
from pathlib import Path
import plistlib
import re
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "integrations/phone_transfer/shortcut/build_shortcut.py"
SPEC = importlib.util.spec_from_file_location("phone_transfer_shortcut_builder", SOURCE)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


class PhoneTransferShortcutTest(unittest.TestCase):
    def setUp(self):
        self.doc = plistlib.loads(builder.shortcut_xml())
        self.actions = self.doc["WFWorkflowActions"]

    def params(self, label):
        action_id = builder._uuid(label)
        return next(a["WFWorkflowActionParameters"] for a in self.actions
                    if a["WFWorkflowActionParameters"]["UUID"] == action_id)

    def index(self, label):
        action_id = builder._uuid(label)
        return next(i for i, action in enumerate(self.actions)
                    if action["WFWorkflowActionParameters"]["UUID"] == action_id)

    def assert_empty_guard_stops(self, label, source, before):
        """Check that the actual empty branch exits before the protected action."""
        start, end = self.index(label + ":start"), self.index(label + ":end")
        params = self.actions[start]["WFWorkflowActionParameters"]
        self.assertEqual(params["WFCondition"], 101)
        self.assertEqual(params["WFInput"]["Type"], "Variable")
        self.assertEqual(params["WFInput"]["Variable"]["WFSerializationType"], "WFTextTokenAttachment")
        self.assertEqual(params["WFInput"]["Variable"]["Value"], source)
        body = self.actions[start + 1:end]
        self.assertEqual([a["WFWorkflowActionIdentifier"] for a in body],
                         ["is.workflow.actions.showresult", "is.workflow.actions.exit"])
        self.assertLess(end, self.index(before))

    @staticmethod
    def output(label):
        return {"Type": "ActionOutput", "OutputUUID": builder._uuid(label), "OutputName": label}

    def test_repeatable_public_template_has_share_sheet_input_types(self):
        self.assertEqual(builder.shortcut_xml(), builder.shortcut_xml())
        self.assertEqual(self.doc["WFWorkflowName"], "发送到办公电脑 L")
        self.assertEqual(self.doc["WFWorkflowTypes"], ["ActionExtension"])
        self.assertTrue({"WFImageContentItem", "WFGenericFileContentItem", "WFAVAssetContentItem",
                         "WFStringContentItem"}.issubset(self.doc["WFWorkflowInputContentItemClasses"]))
        self.assertFalse(re.search(rb"Bearer [0-9a-f]{64}", builder.shortcut_xml()))
        self.assertFalse(re.search(rb"/upload/[0-9a-f]{64}", builder.shortcut_xml()))

    def test_one_import_question_populates_the_initial_blank_text_action(self):
        questions = self.doc["WFWorkflowImportQuestions"]
        self.assertEqual(len(questions), 1)
        question = questions[0]
        self.assertEqual(question["Category"], "Parameter")
        self.assertEqual(question["ActionIndex"], 0)
        self.assertEqual(question["ParameterKey"], "WFTextActionText")
        self.assertEqual(question["DefaultValue"], "")
        self.assertIn("绑定码", question["Text"])
        target = self.actions[question["ActionIndex"]]
        self.assertEqual(target["WFWorkflowActionIdentifier"], "is.workflow.actions.gettext")
        self.assertEqual(target["WFWorkflowActionParameters"][question["ParameterKey"]], "")
        self.assertEqual(target["WFWorkflowActionParameters"]["UUID"], builder._uuid("installed-config"))

    def test_configuration_has_no_filesystem_or_legacy_setup_url_dependency(self):
        identifiers = [a["WFWorkflowActionIdentifier"] for a in self.actions]
        for identifier in identifiers:
            self.assertFalse(any(part in identifier for part in
                                 ("documentpicker", ".file.", ".folder", "setitemname", "openurl")))
        serialized = builder.shortcut_xml().decode("utf-8")
        for obsolete in ("iCloud", "WFFileLocationType", "WFFileStorageService", "WFGetFilePath",
                         "WFFolder", "WFFileDestinationPath", "suishouchuan-L.json",
                         "suishouchuan-setup-v1:"):
            self.assertNotIn(obsolete, serialized)
        self.assertEqual(sum(identifier == "is.workflow.actions.gettext" for identifier in identifiers), 1)

    def test_action_references_and_control_flow_are_connected(self):
        seen = set()
        stack = []
        for action in self.actions:
            params = action["WFWorkflowActionParameters"]
            for value in walk(params):
                if isinstance(value, dict) and value.get("Type") == "ActionOutput":
                    self.assertIn(value["OutputUUID"], seen)
            if "WFControlFlowMode" in params:
                group = params["GroupingIdentifier"]
                if params["WFControlFlowMode"] == 0:
                    stack.append((group, action["WFWorkflowActionIdentifier"]))
                elif params["WFControlFlowMode"] == 2:
                    self.assertTrue(stack, "An end marker must have a matching start")
                    self.assertEqual(stack.pop(), (group, action["WFWorkflowActionIdentifier"]))
                else:
                    self.fail("Unexpected control-flow branch in the public template")
            self.assertNotIn(params["UUID"], seen)
            seen.add(params["UUID"])
        self.assertEqual(stack, [])

    def test_empty_and_invalid_configuration_stop_before_any_network_action(self):
        self.assert_empty_guard_stops("configured", self.output("installed-config"), "stored:dictionary")
        dictionary = self.params("stored:dictionary")
        self.assertEqual(dictionary["WFInput"]["Value"], self.output("installed-config"))
        self.assertEqual(self.actions[self.index("stored:dictionary")]["WFWorkflowActionIdentifier"],
                         "is.workflow.actions.detect.dictionary")
        for name, pattern in (("url", builder.PREPARE_PATTERN),
                              ("authorization", builder.AUTHORIZATION_PATTERN)):
            with self.subTest(field=name):
                value = self.params("stored:" + name)
                self.assertEqual(value["WFInput"]["Value"], self.output("stored:dictionary"))
                self.assertEqual(value["WFDictionaryKey"], name)
                self.assertEqual(value["WFGetDictionaryValueType"], "Value")
                match = self.params("stored:validate:" + name)
                self.assertEqual(match["WFMatchTextPattern"], pattern)
                self.assertTrue(match["WFMatchTextCaseSensitive"])
                self.assertEqual(match["text"]["Value"]["attachmentsByRange"]["{0, 1}"],
                                 self.output("stored:" + name))
                self.assert_empty_guard_stops("stored:require:" + name,
                                             self.output("stored:validate:" + name), "files-loop:start")
        self.assertLess(self.index("stored:dictionary"), self.index("stored:validate:url"))
        self.assertLess(self.index("stored:require:authorization:end"), self.index("no-shared-files:start"))
        first_http = next(i for i, a in enumerate(self.actions)
                          if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl")
        self.assertGreater(first_http, self.index("no-shared-files:end"))

    def test_configuration_validation_rejects_blank_foreign_origin_and_malformed_credentials(self):
        # ICU uses \z for the exact end anchor; Python's equivalent is \Z.
        prepare = re.compile(builder.PREPARE_PATTERN.replace(r"\z", r"\Z"))
        valid = builder.API_BASE + "/upload/" + "a" * 64 + "/authorize"
        self.assertIsNotNone(prepare.fullmatch(valid))
        for wrong in ["", " ", "{}", valid + "?leak=yes", valid + "\n", valid + "#fragment",
                      "prefix" + valid, valid.replace("https:", "http:"),
                      valid.replace("whatsup.streamlit.app", "example.com"),
                      valid.replace("a" * 64, "a" * 63)]:
            with self.subTest(url=wrong):
                self.assertIsNone(prepare.search(wrong))
        authorization = re.compile(builder.AUTHORIZATION_PATTERN.replace(r"\z", r"\Z"))
        credential = "Bearer " + "b" * 64
        self.assertIsNotNone(authorization.search(credential))
        for wrong in ("", " ", "Bearer ", credential + "\n", " " + credential,
                      "Bearer " + "b" * 63, "Bearer " + "B" * 64, "Bearer " + "g" * 64):
            with self.subTest(authorization=wrong):
                self.assertIsNone(authorization.search(wrong))

    def test_no_input_only_checks_configuration_and_exits_without_upload(self):
        self.assert_empty_guard_stops("no-shared-files", {"Type": "ExtensionInput"}, "files-loop:start")
        self.assertLess(self.index("stored:require:authorization:end"), self.index("no-shared-files:start"))
        self.assertEqual(self.params("configuration-ready:stop")["UUID"],
                         self.actions[self.index("no-shared-files:end") - 1]["WFWorkflowActionParameters"]["UUID"])
        loop_start, loop_end = self.index("files-loop:start"), self.index("files-loop:end")
        for i, action in enumerate(self.actions):
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl":
                self.assertLess(loop_start, i)
                self.assertLess(i, loop_end)

    def test_authorize_then_upload_uses_json_body_and_dynamic_ticket(self):
        http = [a["WFWorkflowActionParameters"] for a in self.actions
                if a["WFWorkflowActionIdentifier"].endswith("downloadurl")]
        self.assertEqual(len(http), 2)
        prepare, upload = http
        self.assertEqual([p["WFHTTPMethod"] for p in http], ["POST", "POST"])
        self.assertEqual([p["WFHTTPBodyType"] for p in http], ["JSON", "Form"])
        fields = prepare["WFJSONValues"]["Value"]["WFDictionaryFieldValueItems"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["WFKey"]["Value"]["string"], "authorization")
        self.assertEqual(fields[0]["WFItemType"], 0)
        self.assertEqual(fields[0]["WFValue"]["Value"]["attachmentsByRange"]["{0, 1}"],
                         self.output("stored:authorization"))
        self.assertEqual(prepare["WFURL"]["Value"]["attachmentsByRange"]["{0, 1}"],
                         self.output("stored:url"))
        for action in http:
            self.assertEqual(action["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"], [])
        ticket = upload["WFURL"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(ticket["OutputUUID"], prepare["UUID"])
        self.assertEqual(self.params("validate-ticket")["WFMatchTextPattern"], builder.TICKET_PATTERN)
        self.assert_empty_guard_stops("ticket-present", self.output("validate-ticket"), "upload-original")

    def test_multipart_preserves_repeat_item_as_file_without_coercion(self):
        loop = self.params("files-loop:start")
        self.assertEqual(loop["WFInput"]["Value"], {"Type": "ExtensionInput"})
        upload = self.params("upload-original")
        fields = upload["WFFormValues"]["Value"]["WFDictionaryFieldValueItems"]
        self.assertEqual(len(fields), 1)
        file = fields[0]
        self.assertEqual(file["WFKey"]["Value"]["string"], "file")
        self.assertEqual(file["WFItemType"], 5)
        self.assertEqual(file["WFValue"]["WFSerializationType"], "WFTokenAttachmentParameterState")
        attachment = file["WFValue"]["Value"]
        self.assertEqual(attachment["WFSerializationType"], "WFTextTokenAttachment")
        self.assertEqual(attachment["Value"], {"Type": "Variable", "VariableName": "Repeat Item"})
        self.assertEqual(upload["WFRequestVariable"], attachment)
        ids = [a["WFWorkflowActionIdentifier"] for a in self.actions]
        self.assertFalse(any(term in identifier for identifier in ids
                             for term in ("image.convert", "image.resize", "encode", "base64", "delete")))
        self.assertFalse(any(isinstance(value, dict) and "Aggrandizements" in value for value in walk(self.doc)))

    def test_display_uses_repeat_results_after_upload_not_the_ticket(self):
        self.assertEqual(self.actions[-1]["WFWorkflowActionIdentifier"], "is.workflow.actions.showresult")
        result = self.params("upload-results")["Text"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(result["OutputUUID"], builder._uuid("files-loop:end"))
        self.assertEqual(self.actions[-3]["WFWorkflowActionParameters"]["UUID"], builder._uuid("upload-original"))


if __name__ == "__main__":
    unittest.main()
