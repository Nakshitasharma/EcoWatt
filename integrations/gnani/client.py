"""Shared Gnani API transport. Service endpoints follow the published speech API docs."""
import requests

BASE_URL = "https://api.vachana.ai"

def request(method: str, path: str, key: str, **kwargs):
    response = requests.request(method, BASE_URL + path, headers={"X-API-Key-ID": key, **kwargs.pop("headers", {})}, timeout=(5, 60), **kwargs)
    response.raise_for_status()
    return response
