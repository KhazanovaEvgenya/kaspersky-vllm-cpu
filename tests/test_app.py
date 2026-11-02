import asyncio
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.modules.setdefault("huggingface_hub", types.SimpleNamespace(snapshot_download=Mock()))
import download_model
from privacy import AuditMiddleware, SafeFormatter


class AppTests(unittest.TestCase):
    def test_cache_does_not_access_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            env = {"MODEL_ID": "test/model", "MODEL_REVISION": "abc"}
            with patch.dict("os.environ", env), patch.object(
                download_model, "Path", return_value=target
            ), patch.object(download_model, "snapshot_download") as fetch:
                download_model.download_model()
                fetch.assert_called_once()
                self.assertTrue((target / ".complete.json").exists())
                fetch.reset_mock()
                download_model.download_model()
                fetch.assert_not_called()

    def test_failed_download_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            with patch.dict("os.environ", {"MODEL_ID": "test", "MODEL_REVISION": "abc"}), patch.object(
                download_model, "Path", return_value=target
            ), patch.object(download_model, "snapshot_download", side_effect=OSError):
                with self.assertRaises(OSError):
                    download_model.download_model()
                self.assertFalse((target / ".complete.json").exists())

    def test_logging_removes_messages_and_exceptions(self):
        record = logging.LogRecord("vllm", logging.ERROR, "", 1, "PROMPT %s", ("ANSWER",), None)
        record.exc_text = "SECRET traceback"
        result = SafeFormatter().format(record)
        for secret in ["PROMPT", "ANSWER", "SECRET"]:
            self.assertNotIn(secret, result)

    def test_audit_keeps_status_without_body(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SafeFormatter())
        logger = logging.getLogger("inference.audit")
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        async def application(scope, receive, send):
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"SECRET ANSWER"})

        async def send(message):
            pass

        asyncio.run(AuditMiddleware(application)(
            {"type": "http", "path": "/v1/chat/completions"}, None, send
        ))
        self.assertIn("status=200", stream.getvalue())
        self.assertNotIn("SECRET", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
