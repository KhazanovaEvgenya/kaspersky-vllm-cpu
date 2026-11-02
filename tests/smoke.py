"""Проверка работающего API на localhost:8000; токен берётся из .env."""
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
settings = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines() if "=" in line)
url = "http://127.0.0.1:8000/v1/chat/completions"
prompt = "Reply with one sentence about Kubernetes. Test ID: " + uuid.uuid4().hex
body = json.dumps({"model": "qwen", "messages": [{"role": "user", "content": prompt}], "max_tokens": 32}).encode()

for token in [None, "invalid-token"]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=30)
        raise AssertionError("API accepted an invalid token")
    except urllib.error.HTTPError as error:
        assert error.code == 401, error.code

request = urllib.request.Request(url, body, {
    "Content-Type": "application/json", "Authorization": "Bearer " + settings["API_TOKEN"]
})
with urllib.request.urlopen(request, timeout=300) as response:
    result = json.load(response)
answer = result["choices"][0]["message"]["content"]
assert answer.strip(), "Empty model response"
logs = subprocess.check_output([
    str(root / ".tools" / "kubectl.exe"), "--context", "kasperskiy",
    "logs", "deployment/inference", "-c", "vllm"
], text=True, encoding="utf-8")
assert prompt not in logs, "Prompt leaked into logs"
assert answer not in logs, "Answer leaked into logs"
assert settings["API_TOKEN"] not in logs, "Token leaked into logs"
assert "status=200" in logs, "Request audit missing"
print("OK: missing/invalid token -> 401; inference -> 200; audit present; no text/token leaks")
