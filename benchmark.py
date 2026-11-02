"""Streaming load test using only the Python standard library."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time
import urllib.request
import uuid


def request(base_url, token, repeats, index, max_tokens):
    prompt = f"Request {index}. " + (
        "A small service receives data and stores it for later processing. " * repeats
    ) + "Summarize this in two sentences."
    payload = {
        "model": "qwen", "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0, "stream": True,
        "stream_options": {"include_usage": True},
        "ignore_eos": True,
    }
    req = urllib.request.Request(
        base_url + "/v1/chat/completions", json.dumps(payload).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    started = time.perf_counter()
    first_token = None
    usage = None
    done = False
    with urllib.request.urlopen(req, timeout=300) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                done = True
                break
            event = json.loads(data)
            if "error" in event:
                raise RuntimeError("Server returned a streaming error")
            if first_token is None and any(
                choice.get("delta", {}).get("content") for choice in event.get("choices", [])
            ):
                first_token = time.perf_counter() - started
            if event.get("usage"):
                usage = event["usage"]
    latency = time.perf_counter() - started
    if not done or first_token is None or not usage or not usage["completion_tokens"]:
        raise RuntimeError("Incomplete stream or missing usage")
    return {
        "ttft_s": first_token, "latency_s": latency,
        "prompt_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--output", default="benchmark-results.json")
    args = parser.parse_args()
    if min(args.requests, args.concurrency, args.max_tokens) < 1:
        parser.error("counts must be positive")
    settings_path = Path(__file__).with_name(".env")
    settings = dict(line.split("=", 1) for line in settings_path.read_text().splitlines() if "=" in line) if settings_path.exists() else {}
    token = os.environ.get("API_TOKEN") or settings.get("API_TOKEN")
    if not token:
        parser.error("set API_TOKEN or create .env")
    results = {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
               "requests": args.requests, "concurrency": args.concurrency,
               "max_tokens": args.max_tokens, "cases": {}}
    for name, repeats in [("short", 1), ("long", 90)]:
        # Прогрев и компиляция не входят в измеряемый интервал.
        request(args.url, token, repeats, uuid.uuid4().hex + "-warmup", args.max_tokens)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            rows = list(pool.map(
                lambda i: request(args.url, token, repeats, f"{uuid.uuid4().hex}-{name}-{i}", args.max_tokens),
                range(args.requests),
            ))
        duration = time.perf_counter() - started
        case = {
            "mean_prompt_tokens": statistics.mean(row["prompt_tokens"] for row in rows),
            "mean_ttft_s": statistics.mean(row["ttft_s"] for row in rows),
            "mean_latency_s": statistics.mean(row["latency_s"] for row in rows),
            "output_tokens_per_s": sum(row["output_tokens"] for row in rows) / duration,
            "requests_per_s": len(rows) / duration,
            "duration_s": duration, "samples": rows,
        }
        results["cases"][name] = case
        print(f"{name}: input={case['mean_prompt_tokens']:.0f} tokens; "
              f"TTFT={case['mean_ttft_s']:.3f}s; latency={case['mean_latency_s']:.3f}s; "
              f"throughput={case['output_tokens_per_s']:.2f} tokens/s, "
              f"{case['requests_per_s']:.3f} requests/s", flush=True)
    Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
