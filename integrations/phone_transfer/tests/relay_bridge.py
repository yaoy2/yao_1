"""Test-only JSON-lines adapter: exercises the production broker without Streamlit."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.phone_transfer_relay import RelayBroker  # noqa: E402

broker = RelayBroker()
for line in sys.stdin:
    request = json.loads(line)
    response = broker.exchange(request["request"])
    print(json.dumps({"id": request["id"], "response": response}), flush=True)
