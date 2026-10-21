#!/bin/sh
set -eu

echo 'Checking Worker tools and workspace'
[ "$(uname -m)" = x86_64 ]
[ "${PWNMESH_WORKER_ENVIRONMENT:-}" = kali-headless ] || {
    echo 'Expected the full kali-headless Worker image' >&2; exit 1;
}
[ "$(id -u)" = 0 ]
[ -d /workspace/.git ]
[ "$(readlink -f /home/kali/workspace)" = /workspace ]
[ -s /etc/ssl/certs/ca-certificates.crt ]
[ -x "${PLAYWRIGHT_MCP_EXECUTABLE_PATH:-/missing}" ]
for tool in pwnmesh pwn-http bash curl rg fd jq git python python3 pip node npm \
    nmap sqlmap java javac jadx apktool sqlite3 aws tccli aliyun playwright-cli; do
    command -v "$tool" >/dev/null || { echo "Missing Worker tool: $tool" >&2; exit 1; }
done
pwnmesh worker --help >/dev/null
nmap --version >/dev/null
playwright-cli --version >/dev/null

echo 'Checking Python dependencies and local HTTP replay'
PWNLIB_NOTERM=1 python - <<'PY'
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import awscli
import pwn
import pymongo

assert sys.version_info[:2] == (3, 13), sys.version
assert sys.prefix == "/opt/pwnmesh-venv", sys.prefix
assert pwn.asm("nop", arch="amd64") == b"\x90"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"pwnmesh-worker-smoke"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

with HTTPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as tmp:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        capture, output = Path(tmp) / "request.http", Path(tmp) / "evidence"
        capture.write_bytes(b"GET / HTTP/1.1\r\n\r\n")
        replay = subprocess.run(["pwn-http", "replay", str(capture), "--index", "1",
            "--base-url", f"http://127.0.0.1:{server.server_port}", "--output", str(output),
            "--timeout", "5"], check=True, capture_output=True, text=True, timeout=10)
        result = json.loads(replay.stdout)
        assert result.get("status") == 200 and result.get("complete"), result
        assert (output / "response.body").read_bytes() == b"pwnmesh-worker-smoke"
    finally:
        server.shutdown()
        thread.join(timeout=2)
PY
/opt/tccli-venv/bin/python -c 'import tccli, tencentcloud'

echo 'Checking headless Chromium'
node - "$(npm root -g)/@playwright/cli/node_modules/playwright-core" <<'JS'
const { chromium } = require(process.argv[2]);
(async () => {
  if (Number(process.versions.node.split('.')[0]) < 20) throw Error('Node.js 20+ required');
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_MCP_EXECUTABLE_PATH,
    headless: true, chromiumSandbox: false, timeout: 15000,
  });
  try {
    const page = await browser.newPage();
    await page.setContent('<title>PwnMesh smoke</title>');
    if (await page.title() !== 'PwnMesh smoke') throw Error('Chromium page check failed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
JS

echo 'Worker smoke checks passed'
