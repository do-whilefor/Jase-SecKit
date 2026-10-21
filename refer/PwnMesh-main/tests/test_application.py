"""Offline checks of the packaged CLI, HTTP server and SQLite persistence."""

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.environ["PWNMESH_TEST_BINARY"]
        cls.headless = os.environ.get("PWNMESH_TEST_HEADLESS") == "1"
        cls.directory = tempfile.TemporaryDirectory(prefix="pwnmesh-test-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.env = {
            "PATH": os.defpath,
            "HOME": cls.directory.name,
            "PWNMESH_MODEL_CONFIG_PATH": str(Path(cls.directory.name) / "models.json"),
        }
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        cls.http = build_opener(ProxyHandler({}))
        cls.log = tempfile.TemporaryFile()
        cls.addClassCleanup(cls.log.close)
        cls.process = None
        cls.addClassCleanup(cls.stop_server)
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.process = subprocess.Popen(
            [cls.binary, "serve", "--host", "127.0.0.1", "--port", str(cls.port),
             "--db-path", str(Path(cls.directory.name) / "board.db")],
            cwd=cls.directory.name, env=cls.env, stdout=cls.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and cls.process.poll() is None:
            try:
                status, _, body = cls.request("/health")
                if status == 200 and json.loads(body) == {"status": "ok"}:
                    return
            except (URLError, OSError, ValueError):
                pass
            time.sleep(0.05)
        cls.log.seek(0)
        raise AssertionError("Server did not become healthy:\n" + cls.log.read().decode(errors="replace"))

    @classmethod
    def stop_server(cls):
        if cls.process is None:
            return
        if cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=2)
                raise AssertionError("Server did not stop after SIGTERM")
        if cls.process.returncode != 0:
            raise AssertionError(f"Server exited with status {cls.process.returncode}")

    @classmethod
    def request(cls, path, method="GET", data=None):
        request = Request(
            f"http://127.0.0.1:{cls.port}" + path, method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = cls.http.open(request, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def json_request(self, path, method="GET", data=None, expected=200):
        status, headers, body = self.request(path, method, data)
        self.assertEqual(status, expected, body.decode(errors="replace"))
        self.assertEqual(headers.get_content_type(), "application/json")
        return json.loads(body)

    def test_cli(self):
        for command in ([], ["serve"], ["dispatch"], ["worker"]):
            with self.subTest(command=command):
                result = subprocess.run(
                    [self.binary, *command, "--help"], env=self.env,
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Usage", result.stdout + result.stderr)
        result = subprocess.run(
            [self.binary, "unknown-command"], env=self.env,
            capture_output=True, text=True, timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_storage_survives_restart(self):
        self.assertEqual(self.json_request("/projects"), [])
        graph = self.json_request("/projects", "POST", {
            "title": "Smoke project", "origin": "Local fixture",
            "goal": "Verify persistence", "start_paused": True,
        }, expected=201)
        self.assertEqual(graph["project"]["status"], "stopped")
        path = "/projects/" + graph["project"]["id"]
        self.json_request(path + "/title", "PUT", {"title": "Saved title"})
        self.stop_server()
        self.start_server()
        project = self.json_request(path)["project"]
        self.assertEqual(project["title"], "Saved title")
        self.assertEqual(project["status"], "stopped")
        self.assertEqual(self.request(path, "DELETE")[0], 204)
        self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.json_request("/projects"), [])

    def test_web_assets(self):
        if self.headless:
            self.assertEqual(self.request("/")[0], 404)
            self.assertEqual(self.request("/static/index.html")[0], 404)
            return
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "text/html")
        assets = set(re.findall(r'''(?:src|href)=["'](/static/[^"']+\.(?:js|css))["']''', body.decode()))
        self.assertEqual({Path(path).suffix for path in assets}, {".js", ".css"})
        for path in assets:
            with self.subTest(asset=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn(headers.get_content_type(), {"text/css"} if path.endswith(".css")
                              else {"text/javascript", "application/javascript"})


if __name__ == "__main__":
    unittest.main()
