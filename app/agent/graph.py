"""基于 LangGraph 的 ReAct 周报生成编排（项目核心）

节点流转图：
    START → agent ──无工具调用──→ END（周报完成）
              │有工具调用
              ├─轮次未超限─→ tools → agent（ReAct 循环）
              └─轮次超限──→ force_summarize → END（守卫强制收尾）

设计要点：
1. ReAct 循环：大模型自主决策"调哪个工具、传什么参数"，而非硬编码流水线
2. 轮次守卫：iterations 计数 + 条件边，杜绝 Agent 无限死循环
3. 失败容错：工具异常自动重试，重试耗尽把错误信息回传给模型自行调整，
   而不是让整个任务崩溃
4. 短期记忆：checkpointer 按 thread_id 保存全流程状态，支持断点恢复
"""
import time

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agent.memory import build_checkpointer
from app.agent.prompts import FORCE_SUMMARIZE_PROMPT
from app.agent.state import AgentState
from app.config import get_settings
from app.services.metrics import metrics
from app.tools import TOOL_REGISTRY, get_tools

_llm_with_tools: ChatOpenAI | None = None
_llm_plain: ChatOpenAI | None = None


def _get_llms() -> tuple[ChatOpenAI, ChatOpenAI]:
    """惰性初始化：避免导入阶段就要求 API Key 存在"""
    global _llm_with_tools, _llm_plain
    settings = get_settings()
    if _llm_with_tools is None:
        kwargs = {
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
            "temperature": 0.2,
        }
        _llm_with_tools = ChatOpenAI(**kwargs).bind_tools(get_tools())
        _llm_plain = ChatOpenAI(**kwargs)
    return _llm_with_tools, _llm_plain


async def _execute_with_retry(tool_name: str, args: dict) -> str:
    """带重试与指标统计的工具执行；最终失败也返回错误文本供模型自行调整"""
    settings = get_settings()
    last_err: Exception | None = None
    for attempt in range(settings.tool_retry_times + 1):
        start = time.perf_counter()
        try:
            result = await TOOL_REGISTRY[tool_name].ainvoke(args)
            metrics.record_tool(tool_name, success=True,
                                elapsed_ms=(time.perf_counter() - start) * 1000)
            return str(result)
        except Exception as e:  # noqa: BLE001 网络/API 异常统一走重试
            last_err = e
    metrics.record_tool(tool_name, success=False,
                        elapsed_ms=(time.perf_counter() - start) * 1000)
    return f"工具 {tool_name} 调用失败（已重试 {settings.tool_retry_times} 次）：{last_err}"


async def agent_node(state: AgentState) -> dict:
    llm, _ = _get_llms()
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}


async def tools_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    collected = dict(state.get("collected") or {})
    for call in last.tool_calls:
        content = await _execute_with_retry(call["name"], call["args"])
        tool_messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
        collected[call["name"]] = content
    return {"messages": tool_messages, "iterations": state["iterations"] + 1,
            "collected": collected}


async def force_summarize_node(state: AgentState) -> dict:
    """守卫节点：轮次超限后剥离工具能力，强制模型基于已有信息收尾"""
    _, llm_plain = _get_llms()
    messages = [*state["messages"], HumanMessage(content=FORCE_SUMMARIZE_PROMPT)]
    response = await llm_plain.ainvoke(messages)
    return {"messages": [response]}


def route_after_agent(state: AgentState) -> str:
    """条件边：决定 agent 节点之后的走向"""
    last = state["messages"][-1]
    has_tool_calls = bool(getattr(last, "tool_calls", None))
    if not has_tool_calls:
        return END
    if state["iterations"] >= get_settings().agent_max_iterations:
        return "force_summarize"
    return "tools"


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("force_summarize", force_summarize_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_after_agent,
        {"tools": "tools", "force_summarize": "force_summarize", END: END},
    )
    builder.add_edge("tools", "agent")  # ReAct 主循环
    # force_summarize 无出边即终点；checkpointer 提供断点恢复能力
    return builder.compile(checkpointer=build_checkpointer())
