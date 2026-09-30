"""周报生成业务编排：组装输入 → 驱动 Agent → 落库/缓存 → 输出统计"""
import logging
import time
import uuid

from langchain_core.messages import HumanMessage

from app.agent.graph import build_graph
from app.agent.memory import LongTermMemory
from app.agent.prompts import FORMAT_INSTRUCTION, SYSTEM_PROMPT
from app.config import get_settings
from app.models.schemas import GenerateReportRequest
from app.services.metrics import metrics
from app.tools.rag_tool import save_report_to_index

logger = logging.getLogger(__name__)

_graph = None
_ltm = LongTermMemory()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _sum_tokens(messages: list) -> tuple[int, int]:
    """从全流程消息中累计 token 消耗"""
    inp = out = 0
    for m in messages:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            inp += usage.get("input_tokens", 0)
            out += usage.get("output_tokens", 0)
    return inp, out


async def generate_report(req: GenerateReportRequest) -> dict:
    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，请在 .env 中填写后重启服务")

    period = f"{req.since[:10]} ~ {req.until[:10]}"
    run_id = f"{req.team}-{uuid.uuid4().hex[:8]}"

    # 长期记忆：命中缓存则注入上期周报，保持格式延续并减少额外归纳调用
    last_report = await _ltm.get_last_report(req.team)
    task_prompt = FORMAT_INSTRUCTION.format(
        last_report=last_report or "（无历史周报）",
        period=period, repo=req.repo, since=req.since, until=req.until,
    )

    init_state = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ],
        "iterations": 0,
        "collected": {},
        "final_report": "",
    }

    start = time.perf_counter()
    final = await _get_graph().ainvoke(
        init_state, config={"configurable": {"thread_id": run_id}}
    )
    elapsed = time.perf_counter() - start

    report = final["messages"][-1].content
    input_tokens, output_tokens = _sum_tokens(final["messages"])
    # 口径：累计每次并行调用的工具个数，而非含 tool_calls 的消息条数
    tool_calls = sum(
        len(getattr(m, "tool_calls", None) or []) for m in final["messages"]
    )

    # 产出沉淀：向量库（供后续检索）+ Redis 长期记忆（供下期延续）
    try:
        await save_report_to_index(
            report, {"run_id": run_id, "team": req.team, "period": period}
        )
        await _ltm.save_last_report(req.team, report)
    except Exception as e:  # 沉淀失败不影响本次产出
        logger.warning("周报沉淀失败（向量库/Redis）: %s", e)

    metrics.record_run(
        run_id, elapsed, input_tokens, output_tokens,
        tool_calls, final["iterations"],
    )
    return {
        "run_id": run_id,
        "report": report,
        "stats": {
            "elapsed_seconds": round(elapsed, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tool_calls": tool_calls,
            "iterations": final["iterations"],
            "memory_hit": last_report is not None,
        },
    }
