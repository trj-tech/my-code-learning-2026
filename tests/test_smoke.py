"""冒烟测试：不依赖外部服务（无 API Key / Redis / 网络）即可运行"""
import json
from pathlib import Path

from app.tools.feishu_tool import fetch_feishu_docs
from app.tools.task_tool import fetch_task_updates

MOCK_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"


def test_mock_data_files_exist():
    assert (MOCK_DIR / "feishu_docs.json").exists()
    assert (MOCK_DIR / "tasks.json").exists()


async def test_feishu_tool_filters_by_keyword():
    result = await fetch_feishu_docs.ainvoke({"keyword": "支付"})
    assert "支付网关重构设计文档" in result


async def test_task_tool_filters_by_date():
    result = await fetch_task_updates.ainvoke({"since": "2026-09-24", "until": "2026-09-30"})
    # 9-19 的已完成任务不应出现在本周范围
    assert "短信验证码" not in result
    assert "报表导出" in result


def test_tool_registry_has_five_tools():
    from app.tools import TOOL_REGISTRY

    expected = {"fetch_github_commits", "fetch_feishu_docs", "fetch_task_updates", "search_similar_reports"}
    assert expected == set(TOOL_REGISTRY.keys())


def test_mock_json_valid():
    for f in MOCK_DIR.glob("*.json"):
        json.loads(f.read_text(encoding="utf-8"))
