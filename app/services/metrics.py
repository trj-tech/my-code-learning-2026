"""生产级指标统计：Token 消耗、工具调用成功率、任务耗时

内存态实现（单实例足够）；多实例部署时把数据结构换成 Redis 计数器即可。
对外通过 GET /api/v1/metrics 暴露，可对接 Prometheus exporter。
"""
import threading
import time


class MetricsService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tool_stats: dict[str, dict] = {}  # name -> {success, fail, total_ms}
        self._runs: list[dict] = []             # 每次周报生成的运行记录

    def record_tool(self, name: str, success: bool, elapsed_ms: float) -> None:
        with self._lock:
            stat = self._tool_stats.setdefault(
                name, {"success": 0, "fail": 0, "total_ms": 0.0}
            )
            stat["success" if success else "fail"] += 1
            stat["total_ms"] += elapsed_ms

    def record_run(self, run_id: str, elapsed_seconds: float,
                   input_tokens: int, output_tokens: int,
                   tool_calls: int, iterations: int) -> None:
        with self._lock:
            self._runs.append({
                "run_id": run_id,
                "elapsed_seconds": round(elapsed_seconds, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "iterations": iterations,
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            # 只保留最近 100 次，防止内存膨胀
            del self._runs[:-100]

    def snapshot(self) -> dict:
        with self._lock:
            tool_summary = {}
            for name, s in self._tool_stats.items():
                total = s["success"] + s["fail"]
                tool_summary[name] = {
                    "calls": total,
                    "success_rate": round(s["success"] / total, 4) if total else None,
                    "avg_ms": round(s["total_ms"] / total, 1) if total else None,
                }
            return {"tools": tool_summary, "recent_runs": list(reversed(self._runs))}


metrics = MetricsService()
