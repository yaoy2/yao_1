"""In-process test bridge for the production relay and native ASGI upload API."""

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
from starlette.applications import Starlette

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.phone_transfer_api import PhoneTransferRegistry  # noqa: E402
from utils.phone_transfer_relay import RelayBroker  # noqa: E402

broker = RelayBroker()
native = PhoneTransferRegistry(ack_timeout=0)
application = Starlette(routes=native.routes)


async def exchange(request):
    if request.get("kind") != "native":
        return broker.exchange(request)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="https://fixture.invalid") as client:
        response = await client.request(
            request["method"], request["path"], headers=request.get("headers", {}),
            content=base64.b64decode(request.get("bodyBase64", "")),
        )
    return {"status": response.status_code, "headers": dict(response.headers),
            "bodyBase64": base64.b64encode(response.content).decode("ascii")}


with asyncio.Runner() as runner:
    try:
        for line in sys.stdin:
            request = json.loads(line)
            response = runner.run(exchange(request["request"]))
            print(json.dumps({"id": request["id"], "response": response}), flush=True)
    finally:
        if hasattr(native, "close"):
            native.close()
