"""Load test for an OpenAI-compatible vLLM endpoint: TTFT, latency, TPOT and throughput.

Every request streams a chat completion with a fixed output length (ignore_eos), so runs are comparable.
A unique prefix on every prompt defeats vLLM prefix caching, otherwise repeated long prompts skip prefill.
"""

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import httpx

PARAGRAPH = (
    "Kubernetes schedules containers onto nodes, restarts them when they fail and scales them with load. "
    "A Deployment keeps the desired number of pod replicas, a Service gives them a stable address, "
    "and a PersistentVolumeClaim attaches storage that outlives a single pod. "
)
SHORT_PROMPT = "Explain in two sentences what a Kubernetes Deployment does."


def build_prompts(long_repeat):
    return {"short": SHORT_PROMPT, "long": PARAGRAPH * long_repeat + "\nSummarize the text above in three sentences."}


async def one_request(client, url, headers, model, prompt, max_tokens):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": f"[{uuid.uuid4().hex}] {prompt}"}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = time.perf_counter()
    first, usage = None, {}
    async with client.stream("POST", url, headers=headers, json=body) as response:
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {(await response.aread()).decode()[:500]}")
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if chunk.get("usage"):
                usage = chunk["usage"]
            if first is None and any(c["delta"].get("content") for c in chunk.get("choices", [])):
                first = time.perf_counter()
    ended = time.perf_counter()
    tokens = usage.get("completion_tokens", 0)
    return {
        "ttft": first - started,
        "latency": ended - started,
        "tpot": (ended - first) / (tokens - 1) if tokens > 1 else 0.0,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": tokens,
    }


async def run_scenario(args, prompt, scenario, concurrency):
    headers = {"Authorization": f"Bearer {args.token}"}
    url = f"{args.url.rstrip('/')}/v1/chat/completions"
    limit = asyncio.Semaphore(concurrency)

    async def bounded(client):
        async with limit:
            return await one_request(client, url, headers, args.model, prompt, args.max_tokens)

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        await one_request(client, url, headers, args.model, prompt, 4)
        started = time.perf_counter()
        results = await asyncio.gather(*(bounded(client) for _ in range(args.requests)))
        wall = time.perf_counter() - started

    def p(values, q):
        return statistics.quantiles(values, n=100)[q - 1] if len(values) > 1 else values[0]

    ttft, latency, tpot = ([r[k] for r in results] for k in ("ttft", "latency", "tpot"))
    return {
        "scenario": scenario,
        "concurrency": concurrency,
        "requests": len(results),
        "prompt_tokens": round(statistics.mean(r["prompt_tokens"] for r in results)),
        "output_tokens": round(statistics.mean(r["completion_tokens"] for r in results)),
        "ttft_p50_s": statistics.median(ttft),
        "ttft_p95_s": p(ttft, 95),
        "latency_p50_s": statistics.median(latency),
        "latency_p95_s": p(latency, 95),
        "tpot_p50_ms": statistics.median(tpot) * 1000,
        "throughput_tok_s": sum(r["completion_tokens"] for r in results) / wall,
        "throughput_req_s": len(results) / wall,
    }


def to_markdown(rows):
    header = (
        "| Prompt | Concurrency | Requests | Prompt tok | Output tok | TTFT p50, s | TTFT p95, s | "
        "Latency p50, s | Latency p95, s | TPOT p50, ms | Throughput, tok/s | Throughput, req/s |"
    )
    lines = [header, "|" + "---|" * 12]
    for r in rows:
        lines.append(
            f"| {r['scenario']} | {r['concurrency']} | {r['requests']} | {r['prompt_tokens']} | {r['output_tokens']} | "
            f"{r['ttft_p50_s']:.2f} | {r['ttft_p95_s']:.2f} | {r['latency_p50_s']:.2f} | {r['latency_p95_s']:.2f} | "
            f"{r['tpot_p50_ms']:.0f} | {r['throughput_tok_s']:.1f} | {r['throughput_req_s']:.2f} |"
        )
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--token", default=os.environ.get("API_BEARER_TOKEN"))
    parser.add_argument("--model", default="qwen2.5-1.5b-instruct")
    parser.add_argument("--scenarios", nargs="+", default=["short", "long"], choices=["short", "long"])
    parser.add_argument("--long-repeat", type=int, default=30, help="paragraph repeats in the long prompt")
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--requests", type=int, default=8, help="requests per scenario and concurrency level")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()
    if not args.token:
        parser.error("pass --token or set API_BEARER_TOKEN")

    prompts = build_prompts(args.long_repeat)
    rows = []
    for scenario in args.scenarios:
        for concurrency in args.concurrency:
            print(f"running {scenario} prompt, concurrency {concurrency} ...", flush=True)
            rows.append(await run_scenario(args, prompts[scenario], scenario, concurrency))

    table = to_markdown(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(rows, indent=2))
    (args.out / "results.md").write_text(table + "\n")
    print(table)


if __name__ == "__main__":
    asyncio.run(main())
