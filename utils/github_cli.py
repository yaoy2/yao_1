"""GitHub transport that reuses the local gh login without reading its token."""

import json
import os
import re
import subprocess
from urllib.parse import urlencode, urlsplit


class GitHubCliSession:
    """Reuse gh's login locally without extracting or persisting its credentials."""

    def __init__(self, executable):
        self.executable = executable

    def _request(self, method, url, params=None, json_body=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValueError("GitHub CLI 仅允许访问 GitHub API。")
        endpoint = parsed.path.lstrip("/")
        if params:
            endpoint += "?" + urlencode(params)
        command = [self.executable, "api", "--hostname", "github.com", "--include", "--method", method, endpoint]
        if json_body is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(json_body) if json_body is not None else None,
                                text=True, encoding="utf-8", capture_output=True, timeout=45,
                                env={**os.environ, "GH_PROMPT_DISABLED": "1"})
        output = result.stdout.replace("\r\n", "\n")
        header, _, body = output.partition("\n\n")
        status = re.match(r"HTTP/\S+\s+(\d{3})", header)
        if not status:
            raise RuntimeError("无法通过本机 GitHub CLI 读取服务，请检查 gh 登录和网络；保存结果尚未确认。")
        response = type("GitHubCliResponse", (), {})()
        response.status_code = int(status[1])
        response.json = lambda: json.loads(body)
        return response

    def get(self, url, *, params=None, **kwargs):
        return self._request("GET", url, params=params)

    def put(self, url, *, json, **kwargs):
        return self._request("PUT", url, json_body=json)

