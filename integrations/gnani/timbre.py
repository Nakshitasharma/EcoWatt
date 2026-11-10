"""Timbre v2.5 REST synthesis using Gnani's documented JSON contract."""
from .client import request

def synthesize(text: str, api_key: str, voice="Nalini", language="en-IN"):
    response = request("POST", "/api/v1/tts/inference", api_key, json={
        "text": text, "voice": voice, "model": "timbre-v2.5", "language": language,
        "speed": 1.0, "audio_config": {"sample_rate": 48000, "num_channels": 1,
            "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}})
    return response.content, response.headers.get("content-type", "audio/wav")
