"""Wisio product names must agree with discoverable connection endpoints."""

import json
from pathlib import Path
import threading
import unittest
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

import bridge


class WisioBrandContractTest(unittest.TestCase):
    def test_prompt_file_has_product_name_and_is_loaded(self):
        self.assertEqual(bridge.PRODUCT_PROMPT_PATH.name, "PromptWisio.md")
        self.assertTrue(bridge.PRODUCT_PROMPT_PATH.is_file())
        self.assertIn("giáo viên tiếng Anh", bridge.PRODUCT_PROMPT_PATH.read_text(encoding="utf-8"))

    def test_wisio_ota_returns_wisio_websocket_endpoint(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_ota_handler("192.168.1.25"))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/wisio/ota/", timeout=3) as response:
                result = json.load(response)
            self.assertEqual(result["websocket"]["url"], "ws://192.168.1.25:8000/wisio/v1/")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__": unittest.main()
