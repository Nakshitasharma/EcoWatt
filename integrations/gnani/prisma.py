"""Prisma v3.0 speech-to-text: POST /stt/v3, multipart audio_file."""
from .client import request

def transcribe(audio: bytes, filename: str, content_type: str, api_key: str, language_code="indic-auto", output_format="verbatim"):
    response = request("POST", "/stt/v3", api_key,
        files={"audio_file": (filename, audio, content_type)},
        data={"model": "prisma-v3.0", "language_code": language_code, "format": output_format})
    payload = response.json()
    if not payload.get("success") or not payload.get("transcript"):
        raise ValueError("Prisma response did not include a successful transcript")
    return payload
