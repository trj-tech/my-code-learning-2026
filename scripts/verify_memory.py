"""缓存验证：连续生成两次，对比 memory_hit 与 token 消耗"""
import time

import httpx


def gen(tag: str):
    t0 = time.perf_counter()
    r = httpx.post(
        "http://127.0.0.1:8000/api/v1/reports/generate",
        json={
            "repo": "trj-tech/my-code-learning-2026",
            "since": "2026-09-22T00:00:00Z",
            "until": "2026-09-30T23:59:59Z",
            "team": "trj-tech",
        },
        timeout=300,
    )
    d = r.json()
    s = d["stats"]
    print(f"[{tag}] memory_hit={s['memory_hit']}  input_tokens={s['input_tokens']}  "
          f"elapsed={s['elapsed_seconds']}s  wall={time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    gen("run1-cold")
    gen("run2-warm")
