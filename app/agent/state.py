"""AgentState：LangGraph 全局状态定义，节点间流转的唯一数据载体"""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # 对话消息流（Human / AIMessage / ToolMessage），add_messages 自动追加
    messages: Annotated[list, add_messages]
    # 已完成的工具调用轮次（守卫计数器，防止无限循环）
    iterations: int
    # 各工具采集到的原始数据（供调试与指标统计）
    collected: dict[str, Any]
    # 最终生成的周报文本
    final_report: str
