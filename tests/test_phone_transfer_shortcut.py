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

    def test_repeatable_public_template_has_share_sheet_input_types(self):
        self.assertEqual(builder.shortcut_xml(), builder.shortcut_xml())
        self.assertEqual(self.doc["WFWorkflowName"], "发送到办公电脑 L")
        self.assertEqual(self.doc["WFWorkflowTypes"], ["ActionExtension"])
        self.assertTrue({"WFImageContentItem", "WFGenericFileContentItem", "WFAVAssetContentItem",
                         "WFStringContentItem"}.issubset(self.doc["WFWorkflowInputContentItemClasses"]))
        self.assertFalse(re.search(rb"Bearer [0-9a-f]{64}", builder.shortcut_xml()))
        self.assertEqual(self.doc["WFWorkflowImportQuestions"], [])

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
                    stack.append(group)
                elif params["WFControlFlowMode"] == 2:
                    self.assertEqual(stack.pop(), group)
            self.assertNotIn(params["UUID"], seen)
            seen.add(params["UUID"])
        self.assertEqual(stack, [])

    def test_setup_type_check_uses_runtime_text_type_and_exact_prefix(self):
        type_condition = self.params("text-input:start")
        reference = type_condition["WFConditionalActionString"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(reference["OutputUUID"], builder._uuid("text-type"))
        self.assertEqual(self.params("single-input:start")["WFNumberValue"], 1)
        self.assertEqual(self.params("setup-input:start")["WFCondition"], 8)
        self.assertEqual(self.params("setup-input:start")["WFConditionalActionString"]["Value"]["string"],
                         builder.SETUP_PREFIX)
        self.assertTrue(self.params("setup-json")["WFReplaceTextRegularExpression"])

    def test_configuration_has_an_exact_filename_and_one_explicit_icloud_root(self):
        saves = [a for a in self.actions if a["WFWorkflowActionIdentifier"].endswith("documentpicker.save")]
        self.assertEqual(len(saves), 1)
        save, load = self.params("save-config"), self.params("load-config")
        named = self.params("name-config")
        self.assertEqual(save["WFFolder"], load["WFFile"])
        location = load["WFFile"]["fileLocation"]
        self.assertEqual(location["WFFileLocationType"], "iCloud")
        self.assertEqual(location["relativeSubpath"], "com~apple~CloudDocs")
        self.assertNotIn("crossDeviceItemID", location)
        self.assertNotIn("WFFileStorageService", save)
        self.assertNotIn("WFFileStorageService", load)
        self.assertEqual(named["WFName"], "suishouchuan-L.json")
        self.assertFalse(named["WFDontIncludeFileExtension"])
        self.assertEqual(save["WFFileDestinationPath"], "/")
        self.assertEqual(load["WFGetFilePath"], save["WFFileDestinationPath"] + named["WFName"])
        self.assertFalse(save["WFAskWhereToSave"])
        self.assertTrue(save["WFSaveFileOverwrite"])
        self.assertFalse(load["WFFileErrorIfNotFound"])
        self.assertEqual(save["WFInput"]["Value"]["OutputUUID"], named["UUID"])
        self.assertEqual(named["WFInput"]["Value"]["OutputUUID"], builder._uuid("setup-json"))
        indices = {a["WFWorkflowActionParameters"]["UUID"]: i for i, a in enumerate(self.actions)}
        self.assertLess(indices[builder._uuid("setup-complete:stop")], indices[builder._uuid("prepare-upload")])

    def test_binding_success_requires_independent_readback_of_the_exact_saved_configuration(self):
        readback = dict(self.params("verify-config-file"))
        readback.pop("UUID")
        sending = dict(self.params("load-config"))
        sending.pop("UUID")
        self.assertEqual(readback, sending, "Binding and sending must read the same file with the same action parameters")
        present = self.params("verify-config-present:start")
        self.assertEqual(present["WFCondition"], 101)
        self.assertEqual(present["WFInput"]["Variable"]["Value"]["OutputUUID"], builder._uuid("verify-config-file"))
        text = self.params("verify-config-text")
        self.assertEqual(text["WFInput"]["Value"]["OutputUUID"], builder._uuid("verify-config-file"))
        comparison = self.params("verify-config-differs:start")
        self.assertEqual(comparison["WFCondition"], 5)
        self.assertEqual(comparison["WFInput"]["Variable"]["Value"]["OutputUUID"], text["UUID"])
        expected = comparison["WFConditionalActionString"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(expected["OutputUUID"], builder._uuid("setup-json"))
        ids = [a["WFWorkflowActionParameters"]["UUID"] for a in self.actions]
        ordered = ["save-config", "verify-config-file", "verify-config-present:start",
                   "verify-config-present:stop", "verify-config-text", "verify-config-differs:start",
                   "verify-config-mismatch:stop", "verify-config-differs:end", "setup-complete:message"]
        indices = [ids.index(builder._uuid(label)) for label in ordered]
        self.assertEqual(indices, sorted(indices))
        for label in ("verify-config-present:stop", "verify-config-mismatch:stop"):
            self.assertEqual(self.actions[ids.index(builder._uuid(label))]["WFWorkflowActionIdentifier"], "is.workflow.actions.exit")

    def test_begins_with_receives_typed_text_not_generic_list_item(self):
        # Real iPhone failure: If [Item from List] begins with [prefix] reports
        # a missing parameter. Text materialization must be inside the text
        # branch and must not change the original shared-file loop input.
        actions = {a["WFWorkflowActionParameters"]["UUID"]: a for a in self.actions}
        condition = self.params("setup-input:start")
        input_uuid = condition["WFInput"]["Variable"]["Value"]["OutputUUID"]
        text_action = actions[input_uuid]
        self.assertEqual(text_action["WFWorkflowActionIdentifier"], "is.workflow.actions.gettext")
        reference = text_action["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(reference["OutputUUID"], builder._uuid("first-input"))
        replacement_input = self.params("setup-json")["WFInput"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(replacement_input["OutputUUID"], input_uuid)
        indices = {a["WFWorkflowActionParameters"]["UUID"]: i for i, a in enumerate(self.actions)}
        self.assertLess(indices[builder._uuid("text-input:start")], indices[input_uuid])
        self.assertLess(indices[input_uuid], indices[builder._uuid("setup-input:start")])
        self.assertEqual(self.params("files-loop:start")["WFInput"]["Value"], {"Type": "ExtensionInput"})

    def test_setup_and_stored_configuration_validate_origin_and_authorization(self):
        # ICU uses \z for the exact end anchor; Python's equivalent is \Z.
        prepare = re.compile(builder.PREPARE_PATTERN.replace(r"\z", r"\Z"))
        valid = builder.API_BASE + "/upload/" + "a" * 64 + "/authorize"
        self.assertIsNotNone(prepare.fullmatch(valid))
        for wrong in [valid + "?leak=yes", valid + "\n", valid.replace("https:", "http:"),
                      valid.replace("whatsup.streamlit.app", "example.com")]:
            self.assertIsNone(prepare.fullmatch(wrong))
        for prefix in ("setup", "stored"):
            self.assertEqual(self.params(prefix + ":validate:url")["WFMatchTextPattern"], builder.PREPARE_PATTERN)
            self.assertEqual(self.params(prefix + ":validate:authorization")["WFMatchTextPattern"],
                             builder.AUTHORIZATION_PATTERN)

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
        for action in http:
            self.assertEqual(action["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"], [])
        ticket = upload["WFURL"]["Value"]["attachmentsByRange"]["{0, 1}"]
        self.assertEqual(ticket["OutputUUID"], prepare["UUID"])
        self.assertEqual(self.params("validate-ticket")["WFMatchTextPattern"], builder.TICKET_PATTERN)

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
