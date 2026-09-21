from pathlib import Path
import json
import secrets

from streamlit.testing.v1 import AppTest


def test_phone_transfer_page_renders_without_starting_a_server():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "pages" / "24_25_phone_transfer.py")).run()
    assert not app.exception
    assert app.title[0].value == "📲 随手传"
    assert (root / "integrations" / "phone_transfer" / "frontend" / "app.js").is_file()
    assert not app.get("file_uploader")  # Only bounded encrypted chunks reach the relay.


def test_component_request_is_processed_and_echoed_on_the_same_run():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "pages" / "24_25_phone_transfer.py"))
    app.session_state["phone-transfer-v1"] = {
        "room": secrets.token_hex(32), "relay_key": secrets.token_hex(32),
        "client_id": secrets.token_hex(16), "role": "receiver", "ack": 0,
        "packets": [], "request_id": "component-roundtrip",
    }
    app.run()
    assert not app.exception
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["request_id"] == "component-roundtrip"
    assert args["relay"] == {"ok": True, "peers": [], "messages": [], "accepted": []}


def test_component_registration_survives_a_page_without_an_imported_module():
    path = str(Path(__file__).resolve().parents[1] / "pages" / "24_25_phone_transfer.py")
    app = AppTest.from_string(
        f"from pathlib import Path\n"
        f"exec(compile(Path({path!r}).read_text(encoding='utf-8'), {path!r}, 'exec'), "
        f"{{'__name__': 'detached_transfer_page', '__file__': {path!r}}})"
    ).run()
    assert not app.exception
    assert app.get("component_instance")
