import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rag_endpoint import app


class ChatUiTests(unittest.TestCase):
    def test_get_request_returns_chat_page(self):
        with tempfile.TemporaryDirectory() as directory:
            chat_path = Path(directory) / "chat.html"
            chat_path.write_text("<html><body>Chat</body></html>", encoding="utf-8")

            with patch.object(app, "CHAT_UI_PATH", chat_path):
                result = app.handler({"requestContext": {"http": {"method": "GET"}}}, None)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["headers"]["content-type"], "text/html; charset=utf-8")
        self.assertIn("<body>Chat</body>", result["body"])


if __name__ == "__main__":
    unittest.main()
