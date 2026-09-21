"""Build the public, unsigned iOS Shortcut template; never embed binding secrets.

The caller signs the generated XML separately. Setup input is SETUP_PREFIX plus
a JSON object with ``url`` and ``authorization``. Only that configuration is saved
in iCloud Drive/Shortcuts; shared files go directly to a multipart file field.

Action names/parameters follow Cherri's actions/{basic,documents,web,text}.cherri
and shortcutgen.go. The multipart file wrapper follows the exported-shortcut
reference in viticci/shortcuts-playground-plugin's PARAMETER_TYPES.md (File = 5).
Static checks do not replace importing/running the signed template on an iPhone.
"""

import argparse
from pathlib import Path
import plistlib
import re
import uuid


SHORTCUT_NAME = "发送到办公电脑 L"
SETUP_PREFIX = "suishouchuan-setup-v1:"
CONFIG_FILE = "suishouchuan-L.json"
API_BASE = "https://whatsup.streamlit.app/~/+/phone-transfer-api/v1"
PREPARE_PATTERN = r"\A" + re.escape(API_BASE) + r"/upload/[0-9a-f]{64}/authorize\z"
TICKET_PATTERN = r"\A" + re.escape(API_BASE) + r"/upload/[0-9a-f]{64}/[0-9a-f]{64}\z"
AUTHORIZATION_PATTERN = r"\ABearer [0-9a-f]{64}\z"
_NAMESPACE = uuid.UUID("bfe4e188-96ce-4cac-8801-5a7bbdf8d64e")


def _uuid(label):
    return str(uuid.uuid5(_NAMESPACE, label)).upper()


def _attachment(value):
    return {"Value": value, "WFSerializationType": "WFTextTokenAttachment"}


def _text(value):
    """Encode a text field, preserving references as token strings."""
    if isinstance(value, dict):
        content = {"string": "\ufffc", "attachmentsByRange": {"{0, 1}": value["Value"]}}
    else:
        content = {"string": value}
    return {"Value": content, "WFSerializationType": "WFTextTokenString"}


def _fields(items):
    return {"Value": {"WFDictionaryFieldValueItems": items},
            "WFSerializationType": "WFDictionaryFieldValue"}


class _Builder:
    def __init__(self):
        self.actions = []

    def action(self, identifier, label, **parameters):
        action_id = _uuid(label)
        parameters["UUID"] = action_id
        self.actions.append({"WFWorkflowActionIdentifier": "is.workflow.actions." + identifier,
                             "WFWorkflowActionParameters": parameters})
        return _attachment({"Type": "ActionOutput", "OutputUUID": action_id, "OutputName": label})

    def begin_if(self, label, source, condition, comparison=None):
        parameters = {"GroupingIdentifier": _uuid(label), "WFControlFlowMode": 0,
                      "WFInput": {"Type": "Variable", "Variable": source}, "WFCondition": condition}
        if comparison is not None:
            if isinstance(comparison, int):
                parameters["WFNumberValue"] = comparison
            else:
                parameters["WFConditionalActionString"] = _text(comparison)
        self.action("conditional", label + ":start", **parameters)

    def end_if(self, label):
        self.action("conditional", label + ":end", GroupingIdentifier=_uuid(label), WFControlFlowMode=2)

    def stop_with(self, label, message):
        self.action("showresult", label + ":message", Text=_text(message))
        self.action("exit", label + ":stop")

    def require(self, label, value, message):
        self.begin_if(label, value, 101)  # Does not have any value.
        self.stop_with(label, message)
        self.end_if(label)

    def match(self, label, value, pattern):
        return self.action("text.match", label, WFMatchTextPattern=pattern,
                           text=_text(value), WFMatchTextCaseSensitive=True)

    def config(self, label, source):
        config = self.action("detect.dictionary", label + ":dictionary", WFInput=source)
        url = self.action("getvalueforkey", label + ":url", WFInput=config,
                          WFDictionaryKey="url", WFGetDictionaryValueType="Value")
        authorization = self.action("getvalueforkey", label + ":authorization", WFInput=config,
                                    WFDictionaryKey="authorization", WFGetDictionaryValueType="Value")
        for name, value, pattern in (("url", url, PREPARE_PATTERN),
                                     ("authorization", authorization, AUTHORIZATION_PATTERN)):
            matches = self.match(label + ":validate:" + name, value, pattern)
            self.require(label + ":require:" + name, matches, "配置无效，请重新扫描办公电脑 L 的配置二维码。")
        return url, authorization


def build_shortcut():
    """Return a reproducible plist document containing no user-specific values."""
    b = _Builder()
    shared = _attachment({"Type": "ExtensionInput"})
    b.require("has-input", shared, "首次使用请扫描办公电脑 L 的配置二维码；发送时从照片或文件的分享菜单运行。")
    count = b.action("count", "input-count", Input=shared, WFCountType="Items")
    b.begin_if("single-input", count, 4, 1)
    first = b.action("getitemfromlist", "first-input", WFInput=shared, WFItemSpecifier="First Item")
    input_type = b.action("getitemtype", "input-type", WFInput=first)
    marker = b.action("gettext", "setup-marker", WFTextActionText=SETUP_PREFIX)
    marker_type = b.action("getitemtype", "text-type", WFInput=marker)
    # Comparing two runtime types works on Chinese and English devices alike.
    b.begin_if("text-input", input_type, 4, marker_type)
    b.begin_if("setup-input", first, 8, SETUP_PREFIX)
    setup_json = b.action("text.replace", "setup-json", WFInput=_text(first),
                          WFReplaceTextFind=r"\A" + re.escape(SETUP_PREFIX), WFReplaceTextReplace="",
                          WFReplaceTextCaseSensitive=True, WFReplaceTextRegularExpression=True)
    b.config("setup", setup_json)
    b.action("documentpicker.save", "save-config", WFInput=setup_json,
             WFFileStorageService="iCloud Drive", WFFileDestinationPath=CONFIG_FILE,
             WFAskWhereToSave=False, WFSaveFileOverwrite=True)
    b.stop_with("setup-complete", "已绑定办公电脑 L。现在可在照片或文件中点分享，选择“发送到办公电脑 L”。")
    b.end_if("setup-input")
    b.end_if("text-input")
    b.end_if("single-input")

    config_file = b.action("documentpicker.open", "load-config", WFFileStorageService="iCloud Drive",
                           WFGetFilePath=CONFIG_FILE, WFShowFilePicker=False,
                           WFFileErrorIfNotFound=False)
    b.require("configured", config_file, "尚未配置，请先扫描办公电脑 L 的配置二维码。")
    url, authorization = b.config("stored", config_file)
    group = _uuid("files-loop")
    b.action("repeat.each", "files-loop:start", GroupingIdentifier=group,
             WFControlFlowMode=0, WFInput=shared)
    ticket = b.action("downloadurl", "prepare-upload", WFURL=_text(url), WFHTTPMethod="POST",
                      WFHTTPBodyType="JSON", WFJSONValues=_fields([
                          {"WFKey": _text("authorization"), "WFItemType": 0,
                           "WFValue": _text(authorization)}]), WFHTTPHeaders=_fields([]))
    ticket_match = b.match("validate-ticket", ticket, TICKET_PATTERN)
    b.require("ticket-present", ticket_match, "暂时无法发送，请在办公电脑 L 保持接收页打开，然后重试。")
    # Never interpolate Repeat Item into text or request a converted image type.
    # File field type 5 plus this wrapper carries its original file representation.
    item = _attachment({"Type": "Variable", "VariableName": "Repeat Item"})
    b.action("downloadurl", "upload-original", WFURL=_text(ticket), WFHTTPMethod="POST",
             WFHTTPBodyType="Form", WFRequestVariable=item, WFFormValues=_fields([
                 {"WFKey": _text("file"), "WFItemType": 5,
                  "WFValue": {"Value": item, "WFSerializationType": "WFTokenAttachmentParameterState"}}
             ]), WFHTTPHeaders=_fields([]))
    results = b.action("repeat.each", "files-loop:end", GroupingIdentifier=group, WFControlFlowMode=2)
    b.action("showresult", "upload-results", Text=_text(results))
    return {
        "WFWorkflowName": SHORTCUT_NAME,
        "WFWorkflowClientVersion": "3036.0.4.2",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59774},
        "WFWorkflowActions": b.actions,
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": ["WFImageContentItem", "WFGenericFileContentItem",
                                               "WFAVAssetContentItem", "WFPDFContentItem", "WFStringContentItem"],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowImportQuestions": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": True,
    }


def shortcut_xml():
    return plistlib.dumps(build_shortcut(), fmt=plistlib.FMT_XML, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Unsigned XML .shortcut output path")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(shortcut_xml())
    print(f"Unsigned Shortcut template written: {args.output}")


if __name__ == "__main__":
    main()
