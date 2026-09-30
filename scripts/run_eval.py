"""评估脚本：量化周报 Agent 的冷/热缓存表现

流程（默认 2 轮）：
  每轮 = 清空 Redis 长期记忆 → 生成（冷启动）→ 立即再生成（热缓存）
采集：耗时 / input tokens / output tokens / 工具调用数 / 记忆命中
输出：终端对比表 + data/eval/agent_runs.csv + 汇总统计

使用：先启动服务 `python -m uvicorn app.main:app --port 8000`，再 `python scripts/run_eval.py`
"""
import asyncio
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import redis as redis_sync

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 允许直接运行脚本

from app.config import get_settings  # noqa: E402

API = "http://127.0.0.1:8000/api/v1"
REQ_BODY = {
    "repo": "trj-tech/my-code-learning-2026",
    "since": "2026-09-22T00:00:00Z",
    "until": "2026-09-30T23:59:59Z",
    "team": "eval",
}
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "eval"


def flush_memory() -> None:
    """清空长期记忆，模拟冷启动（保留其他数据不受影响）"""
    r = redis_sync.from_url(get_settings().redis_url, decode_responses=True)
    for key in r.scan_iter("ltm:*"):
        r.delete(key)
    r.close()


async def generate(client: httpx.AsyncClient) -> dict:
    resp = await client.post(f"{API}/reports/generate", json=REQ_BODY, timeout=300)
    resp.raise_for_status()
    return resp.json()


async def main(rounds: int = 2) -> None:
    # 前置检查：服务必须已在运行
    async with httpx.AsyncClient() as probe:
        try:
            await probe.get(f"{API}/health", timeout=5)
        except httpx.HTTPError:
            raise SystemExit("服务未启动：请先运行 python -m uvicorn app.main:app --port 8000")

    rows: list[dict] = []
    async with httpx.AsyncClient() as client:
        for rnd in range(1, rounds + 1):
            flush_memory()
            t0 = time.perf_counter()
            d = await generate(client)
            wall = time.perf_counter() - t0
            s = d["stats"]
            rows.append({"round": rnd, "mode": "cold", **s, "wall_seconds": round(wall, 2)})

            t0 = time.perf_counter()
            d = await generate(client)
            wall = time.perf_counter() - t0
            s = d["stats"]
            rows.append({"round": rnd, "mode": "warm", **s, "wall_seconds": round(wall, 2)})

    # 落盘 CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "agent_runs.csv"
    fields = ["round", "mode", "elapsed_seconds", "input_tokens", "output_tokens",
              "tool_calls", "iterations", "memory_hit", "wall_seconds"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # 终端对比表
    print(f"\n{'轮次':<4} {'模式':<6} {'耗时s':>7} {'input':>7} {'output':>7} {'工具':>4} {'命中':>4}")
    for r in rows:
        hit = "是" if r["memory_hit"] else "否"
        print(f"{r['round']:<4} {r['mode']:<6} {r['elapsed_seconds']:>7} {r['input_tokens']:>7} "
              f"{r['output_tokens']:>7} {r['tool_calls']:>4} {hit:>4}")

    cold = [r for r in rows if r["mode"] == "cold"]
    warm = [r for r in rows if r["mode"] == "warm"]
    avg = lambda rs, k: sum(r[k] for r in rs) / len(rs)  # noqa: E731
    print("\n===== 汇总（均值）=====")
    print(f"冷启动: 耗时 {avg(cold, 'elapsed_seconds'):.2f}s | input {avg(cold, 'input_tokens'):.0f} | output {avg(cold, 'output_tokens'):.0f}")
    print(f"热缓存: 耗时 {avg(warm, 'elapsed_seconds'):.2f}s | input {avg(warm, 'input_tokens'):.0f} | output {avg(warm, 'output_tokens'):.0f}")
    print(f"耗时降低: {(1 - avg(warm, 'elapsed_seconds') / avg(cold, 'elapsed_seconds')) * 100:.1f}%")
    print(f"input token 变化: {(avg(warm, 'input_tokens') / avg(cold, 'input_tokens') - 1) * 100:+.1f}%")

    # 工具成功率（来自 /metrics）
    async with httpx.AsyncClient() as client:
        m = (await client.get(f"{API}/metrics", timeout=10)).json()
    if m["tools"]:
        print("\n===== 工具调用统计 =====")
        for name, stat in m["tools"].items():
            print(f"{name:<24} 调用 {stat['calls']}  成功率 {stat['success_rate']}  平均 {stat['avg_ms']}ms")

    print(f"\n明细已保存: {csv_path}")
    print(f"采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
