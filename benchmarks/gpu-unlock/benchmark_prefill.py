#!/usr/bin/env python3
"""Benchmark Ollama prompt processing at different context lengths."""

import argparse
import json
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODEL = "pi-qwen35-9b-16k"
URL = "http://127.0.0.1:11434/api/generate"

parser = argparse.ArgumentParser()
parser.add_argument("--label", required=True)
parser.add_argument("--runs", type=int, default=3)
args = parser.parse_args()


def request(payload):
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


def make_prompt(repetitions, run_id):
    # Deterministic input with enough variation for a useful prefill workload.
    lines = [
        f"Trial {run_id:03d}, record {i:05d}: function process_{i % 97}(x) "
        f"returns {(i * 17 + 23) % 100003}. "
        f"Module group {i % 31}; dependency {i % 43}."
        for i in range(repetitions)
    ]
    return (
        "Read the following synthetic source-code inventory. "
        "When finished, answer only READY.\n\n"
        + "\n".join(lines)
        + "\n\nAnswer:"
    )


def benchmark(repetitions):

    payload = {
        "model": MODEL,
        "prompt": "",
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {
            "num_ctx": 16384,
            "num_gpu": 33,
            "num_predict": 16,
            "temperature": 0,
            "seed": 42,
        },
    }

    samples = []

    for run in range(args.runs):
        # Change input for each trial to reduce exact-prompt cache reuse.
        payload["prompt"] = make_prompt(repetitions, run + 1)
        payload["options"]["num_keep"] = 0

        result = request(payload)

        tokens = result.get("prompt_eval_count", 0)
        duration = result.get("prompt_eval_duration", 0) / 1e9

        rate = tokens / duration if duration else None

        sample = {
            "run": run + 1,
            "prompt_tokens": tokens,
            "prompt_seconds": round(duration, 4),
            "prompt_tokens_per_second": round(rate, 2) if rate else None,
            "output_tokens": result.get("eval_count"),
            "done_reason": result.get("done_reason"),
        }

        samples.append(sample)

        print(
            f"  Run {run + 1}: "
            f"{tokens} tokens, "
            f"{sample['prompt_tokens_per_second']} tokens/s",
            flush=True,
        )

    rates = [
        sample["prompt_tokens_per_second"]
        for sample in samples
        if sample["prompt_tokens_per_second"] is not None
    ]

    return {
        "repetitions": repetitions,
        "runs": samples,
        "median_tokens_per_second": round(statistics.median(rates), 2),
    }


def main():
    # Approximate target lengths. We'll record actual token counts.
    workloads = [
        ("short", 30),
        ("medium", 75),
        ("long", 150),
    ]

    output = {
        "label": args.label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "num_ctx": 16384,
        "num_gpu": 33,
        "workloads": [],
    }

    for name, repetitions in workloads:
        print(f"\nBenchmarking {name} prompt...", flush=True)

        result = benchmark(repetitions)
        result["name"] = name
        output["workloads"].append(result)

    path = Path(f"results/prefill-{args.label}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n")

    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
