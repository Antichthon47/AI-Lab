#!/usr/bin/env python3
"""Reproducible GPU GEMM benchmark for GPU-Unlock comparisons."""

import argparse
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import torch


def gpu_info():
    query = (
        "name,driver_version,memory.total,power.limit,"
        "temperature.gpu,clocks.sm,clocks.mem"
    )

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def benchmark_gemm(size, dtype, repeats=5, iterations=20):
    torch.cuda.empty_cache()

    a = torch.randn(size, size, device="cuda", dtype=dtype)
    b = torch.randn(size, size, device="cuda", dtype=dtype)
    c = torch.empty_like(a)

    # Enable TF32 tensor-core arithmetic for FP32 experiments.
    torch.backends.cuda.matmul.allow_tf32 = dtype == torch.float32

    for _ in range(10):
        torch.mm(a, b, out=c)

    torch.cuda.synchronize()

    samples = []

    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)

        start.record()

        for _ in range(iterations):
            torch.mm(a, b, out=c)

        end.record()
        torch.cuda.synchronize()

        elapsed_ms = start.elapsed_time(end) / iterations
        samples.append(elapsed_ms)

    median_ms = statistics.median(samples)

    # Dense square GEMM performs approximately 2*N^3 operations.
    tflops = (2 * size**3) / (median_ms / 1000) / 1e12

    del a, b, c
    torch.cuda.empty_cache()

    return {
        "matrix_size": size,
        "dtype": str(dtype),
        "tf32_allowed": dtype == torch.float32,
        "repeats": repeats,
        "iterations_per_repeat": iterations,
        "median_ms": round(median_ms, 4),
        "min_ms": round(min(samples), 4),
        "max_ms": round(max(samples), 4),
        "tflops": round(tflops, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU unavailable")

    torch.manual_seed(42)

    # Keep the math configuration explicit.
    torch.backends.cuda.matmul.allow_tf32 = False

    results = {
        "label": args.label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kernel": platform.release(),
        "pytorch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": torch.cuda.get_device_capability(0),
        "nvidia_smi_before": gpu_info(),
        "benchmarks": [],
    }

    tests = [
        ("FP16", torch.float16),
        ("BF16", torch.bfloat16),
        ("TF32_allowed", torch.float32),
    ]

    for size in (2048, 4096):
        for name, dtype in tests:
            print(f"Running {name}, matrix {size}x{size}...", flush=True)

            result = benchmark_gemm(size, dtype)
            result["operation"] = name
            results["benchmarks"].append(result)

            print(
                f"  {result['median_ms']:.3f} ms | "
                f"{result['tflops']:.2f} TFLOPS",
                flush=True,
            )

    results["nvidia_smi_after"] = gpu_info()

    output = Path(args.output or f"results/{args.label}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n")

    print(f"\nResults saved to: {output}")


if __name__ == "__main__":
    main()
