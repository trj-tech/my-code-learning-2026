"""研发任务系统工具（当前为 Mock 实现，读取本地 JSON 模拟任务看板）

TODO(M4+): 对接真实任务系统（Jira / TAPD / 飞书项目等），替换 _load_mock_tasks 即可
"""
import json
from pathlib import Path

from langchain_core.tools import tool

MOCK_PATH = Path(__file__).resolve().parents[2] / "data" / "mock" / "tasks.json"


def _load_mock_tasks() -> list[dict]:
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


@tool
async def fetch_task_updates(since: str = "", until: str = "") -> str:
    """拉取团队任务系统在时间范围内有进展的任务（含状态与负责人）。

    Args:
        since: 起始日期，格式 YYYY-MM-DD，可传空
        until: 截止日期，格式 YYYY-MM-DD，可传空
    """
    tasks = _load_mock_tasks()
    hits = [
        t for t in tasks
        if (not since or t["updated_at"] >= since)
        and (not until or t["updated_at"] <= until)
    ]
    if not hits:
        return "该时间范围内没有任务进展记录。"

    lines = [
        f"- [{t['id']}] {t['title']}｜负责人：{t['assignee']}｜状态：{t['status']}｜进展：{t['comment']}"
        for t in hits
    ]
    return f"任务系统共 {len(hits)} 条进展：\n" + "\n".join(lines)
