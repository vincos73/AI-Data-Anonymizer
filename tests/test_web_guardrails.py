from __future__ import annotations

import asyncio
import base64
import json
import unittest

from privacy_guardian.web_app import app


def asgi_request(method: str, path: str, body: bytes = b"", content_type: str | None = None) -> tuple[int, bytes]:
    async def run() -> tuple[int, bytes]:
        response_status = 500
        response_body = bytearray()
        headers = [(b"host", b"localhost")]
        if content_type:
            headers.append((b"content-type", content_type.encode()))
        headers.append((b"content-length", str(len(body)).encode()))

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, object]) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "scheme": "http",
            "server": ("localhost", 80),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
        await app(scope, receive, send)
        return response_status, bytes(response_body)

    return asyncio.run(run())


def multipart_body(
    mode: str,
    *,
    filename: str = "documento.txt",
    content: bytes = b"Mario Rossi",
    passphrase: str | None = None,
) -> tuple[bytes, str]:
    boundary = "web-guardrail-test"
    passphrase_part = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"passphrase\"\r\n\r\n{passphrase}\r\n"
        if passphrase is not None
        else ""
    )
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\n{mode}\r\n"
        f"{passphrase_part}"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def restore_multipart_body(text: str, passphrase: str, mapping: bytes) -> tuple[bytes, str]:
    boundary = "web-restore-test"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n{text}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"passphrase\"\r\n\r\n{passphrase}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"mapping\"; filename=\"mappa.omissis-map\"\r\n"
        "Content-Type: application/json\r\n\r\n"
    ).encode() + mapping + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


class WebGuardrailsTest(unittest.TestCase):
    def test_health_exposes_only_web_modes(self) -> None:
        status, body = asgi_request("GET", "/api/health")

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertNotIn("reversible", payload["modes"])
        self.assertNotIn("reversible", payload["mode_notes"])

    def test_reversible_text_is_rejected(self) -> None:
        body = json.dumps({"text": "Mario Rossi", "mode": "reversible", "passphrase": "segreta"}).encode()
        status, response_body = asgi_request("POST", "/api/anonymize", body, "application/json")
        self.assertEqual(status, 400)
        self.assertIn("solo nell'app desktop", json.loads(response_body)["detail"])

    def test_restore_is_rejected_in_web_app(self) -> None:
        restore_body, content_type = restore_multipart_body("<PERSONA_1>", "segreta", b"not-used")
        status, response_body = asgi_request("POST", "/api/restore", restore_body, content_type)

        self.assertEqual(status, 400)
        self.assertIn("app desktop", json.loads(response_body)["detail"])

    def test_restore_is_not_exposed(self) -> None:
        body, content_type = restore_multipart_body("<PERSONA_1>", "segreta", b"not-json")
        status, response_body = asgi_request("POST", "/api/restore", body, content_type)

        self.assertEqual(status, 400)
        self.assertIn("app desktop", json.loads(response_body)["detail"])

    def test_document_endpoints_reject_reversible_pdf(self) -> None:
        for path in ("/api/analyze-document", "/api/anonymize-document"):
            body, content_type = multipart_body("reversible", filename="documento.pdf", passphrase="segreta")
            status, response_body = asgi_request("POST", path, body, content_type)

            self.assertEqual(status, 400)
            self.assertIn("app desktop", json.loads(response_body)["detail"])

    def test_static_ui_hides_reversible_flow_and_uses_safe_processing_fallback(self) -> None:
        html = asgi_request("GET", "/")[1].decode()
        javascript = asgi_request("GET", "/static/app.js")[1].decode()

        self.assertNotIn('value="reversible"', html)
        self.assertIn('Elaborazione sul server OMISSIS configurato.', html)
        self.assertIn("location.hostname", javascript)
        self.assertIn("i dati restano sul dispositivo", javascript)
        self.assertIn("i dati vengono inviati a questo server", javascript)
