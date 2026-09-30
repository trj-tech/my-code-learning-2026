"""工具注册表：Agent 可调用的全部工具统一在此登记，graph 据此绑定与分发"""
from langchain_core.tools import BaseTool

from app.tools.feishu_tool import fetch_feishu_docs
from app.tools.github_tool import fetch_github_commits
from app.tools.rag_tool import search_similar_reports
from app.tools.task_tool import fetch_task_updates

TOOL_REGISTRY: dict[str, BaseTool] = {
    tool.name: tool
    for tool in (fetch_github_commits, fetch_feishu_docs, fetch_task_updates, search_similar_reports)
}


def get_tools() -> list[BaseTool]:
    return list(TOOL_REGISTRY.values())
