"""Sign only our generic template, then verify its complete action definition.

Maintainer tool, never called by the web app. Python 3.12 with python-aea==1.1.0
and its dependencies is needed for cross-platform AEA signature verification.
HubSign's request contract is the one used by electrikmilk/cherri/signing.go.
No receiver configuration, photo or account credential is sent to that service.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import struct
import urllib.request

from build_shortcut import build_shortcut


def verify(data, expected):
    import aea
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization

    if len(data) < 12 or data[:4] != b"AEA1":
        raise ValueError("Signing service did not return an AEA shortcut")
    profile, auth_size = struct.unpack_from("<II", data, 4)
    if profile != 0 or not 0 < auth_size < len(data) - 12:
        raise ValueError("Unexpected signing envelope")
    metadata = plistlib.loads(data[12:12 + auth_size])
    chain = [x509.load_der_x509_certificate(value) for value in metadata["SigningCertificateChain"]]
    # Pinned from Apple's published AppleRootCA-G3.cer, fetched independently.
    root_fingerprint = chain[-1].fingerprint(hashes.SHA256()).hex()
    if root_fingerprint != "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179":
        raise ValueError("Signer is not chained to the verified Apple Root CA G3")
    now = datetime.now(timezone.utc)
    if any(not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc for cert in chain):
        raise ValueError("Signing certificate is outside its validity period")
    for cert, issuer in zip(chain, chain[1:]):
        cert.verify_directly_issued_by(issuer)
    key = chain[0].public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    payload = aea.decode(data, signature_pub=key)
    if not payload.startswith(b"AA01"):
        raise ValueError("Unexpected Apple archive")
    start = payload.find(b"bplist00")
    if start < 0:
        raise ValueError("No workflow in signed archive")
    actual = plistlib.loads(payload[start:])
    # Apple's signer normalizes these envelope-level metadata values. It drops
    # the name (the download filename supplies it) and records its own client
    # version. All actions, references, input types and permissions must match.
    expected = dict(expected)
    expected.pop("WFWorkflowName", None)
    expected.pop("WFWorkflowClientVersion", None)
    if actual.pop("WFWorkflowName", "发送到办公电脑 L") != "发送到办公电脑 L":
        raise ValueError("Unexpected shortcut name")
    version = actual.pop("WFWorkflowClientVersion", None)
    if not isinstance(version, str) or not re.fullmatch(r"[0-9.]+", version):
        raise ValueError("Unexpected signing client version")
    if actual.pop("WFWorkflowHasOutputFallback", False) is not False:
        raise ValueError("Unexpected output fallback")
    if actual != expected:
        raise ValueError("Signed workflow differs from our generated template")
    return root_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sign", action="store_true", help="Send the generic template to HubSign; otherwise verify the existing package")
    args = parser.parse_args()
    workflow = build_shortcut()
    target = Path(__file__).with_name("office-L.shortcut")
    if args.sign:
        xml = plistlib.dumps(workflow, fmt=plistlib.FMT_XML, sort_keys=False).decode()
        if re.search(r"Bearer [0-9a-f]{64}", xml):
            raise ValueError("Refusing to send a populated credential to the signer")
        body = json.dumps({"shortcutName": "发送到办公电脑 L", "shortcut": xml}).encode()
        request = urllib.request.Request("https://hubsign.routinehub.services/sign", data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": "cherri/0.4.8",
                                                  "Origin": "https://routinehub.co", "Referer": "https://routinehub.co/"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if not data.startswith(b"AEA1"):
                raise ValueError(f"Signer returned {response.headers.get('content-type')}: {data[:160]!r}")
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Unexpectedly large signing response")
    else:
        data = target.read_bytes()
    root_fingerprint = verify(data, workflow)
    if args.sign:
        target.write_bytes(data)
    print(json.dumps({"verified_workflow": True, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "signer_root_sha256": root_fingerprint}))


if __name__ == "__main__":
    main()
