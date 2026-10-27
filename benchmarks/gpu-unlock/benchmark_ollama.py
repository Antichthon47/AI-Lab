#!/usr/bin/env python3
import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--num-gpu", type=int, default=None)
parser.add_argument("--label", default="benchmark")
args = parser.parse_args()

MODEL = "pi-qwen35-9b-16k"
URL = "http://127.0.0.1:11434/api/generate"

PROMPT = """
Write a Python function named binary_search that searches a sorted
list of integers and returns the index of a target value, or -1
if the target does not exist.

Include type hints, a docstring, and an explanation of the
algorithm's time and space complexity.
"""

PAYLOAD = {
    "model": MODEL,
    "prompt": PROMPT,
    "stream": False,
    "think": False,
    "keep_alive": "5m",
    "options": {
        "num_ctx": 16384,
        "num_predict": 512,
        "temperature": 0,
        "seed": 42,
    },
}

if args.num_gpu is not None:
    PAYLOAD["options"]["num_gpu"] = args.num_gpu

def generate():
    request = urllib.request.Request(
        URL,
        data=json.dumps(PAYLOAD).encode(),
        headers={"Content-Type": "application/json"},
    )

    start = time.monotonic()

    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.load(response)

    elapsed = time.monotonic() - start

    prompt_tokens = data.get("prompt_eval_count", 0)
    output_tokens = data.get("eval_count", 0)

    prompt_seconds = data.get("prompt_eval_duration", 0) / 1e9
    output_seconds = data.get("eval_duration", 0) / 1e9

    return {
        "wall_seconds": round(elapsed, 3),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "prompt_tokens_per_second": round(
            prompt_tokens / prompt_seconds, 2
        ) if prompt_seconds else None,
        "generation_tokens_per_second": round(
            output_tokens / output_seconds, 2
        ) if output_seconds else None,
        "done_reason": data.get("done_reason"),
    }

print("Warming up Ollama...", flush=True)
generate()

results = []

for i in range(3):
    print(f"Running benchmark {i + 1}/3...", flush=True)
    result = generate()
    results.append(result)
    print(json.dumps(result, indent=2))

generation_rates = [
    r["generation_tokens_per_second"]
    for r in results
    if r["generation_tokens_per_second"] is not None
]

prompt_rates = [
    r["prompt_tokens_per_second"]
    for r in results
    if r["prompt_tokens_per_second"] is not None
]

summary = {
    "model": MODEL,
    "label": args.label,
    "num_gpu": args.num_gpu,
    "context": 16384,
    "num_predict": 512,
    "runs": results,
    "mean_generation_tokens_per_second": round(
        statistics.mean(generation_rates), 2
    ) if generation_rates else None,
    "mean_prompt_tokens_per_second": round(
        statistics.mean(prompt_rates), 2
    ) if prompt_rates else None,
}

output = Path(f"results/ollama-{args.label}.json")
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(summary, indent=2) + "\n")

print("\n=== SUMMARY ===")
print(json.dumps({
    "mean_generation_tokens_per_second":
        summary["mean_generation_tokens_per_second"],
    "mean_prompt_tokens_per_second":
        summary["mean_prompt_tokens_per_second"],
}, indent=2))

print(f"\nSaved to {output}")
