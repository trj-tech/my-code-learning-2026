"""飞书文档工具（当前为 Mock 实现，读取本地 JSON 模拟团队文档库）

TODO(M4): 对接飞书开放平台真实 API，替换 fetch 实现，函数签名与返回格式保持不变：
1. 在飞书开放平台自建企业自建应用，开通 docx:document:readonly 等权限
2. 用 app_id / app_secret 调用 /auth/v3/tenant_access_token/internal 换取租户凭证
3. 调用 /docx/v1/documents/{document_id}/raw_content 拉取正文
"""
import json
from pathlib import Path

from langchain_core.tools import tool

MOCK_PATH = Path(__file__).resolve().parents[2] / "data" / "mock" / "feishu_docs.json"


def _load_mock_docs() -> list[dict]:
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


@tool
async def fetch_feishu_docs(keyword: str, since: str = "", until: str = "") -> str:
    """按关键词检索团队飞书文档（设计文档、评审记录、会议纪要等）。

    Args:
        keyword: 关键词，如 "支付" 或 "评审"；传空字符串返回全部近期文档
        since: 起始日期，格式 YYYY-MM-DD，可传空
        until: 截止日期，格式 YYYY-MM-DD，可传空
    """
    docs = _load_mock_docs()
    hits = [
        d for d in docs
        if (not keyword or keyword in d["title"] or keyword in d["content"])
        and (not since or d["updated_at"] >= since)
        and (not until or d["updated_at"] <= until)
    ]
    if not hits:
        return f"未找到与「{keyword}」相关的文档。"

    lines = [f"- [{d['updated_at']}] 《{d['title']}》：{d['content']}" for d in hits]
    return f"检索到 {len(hits)} 篇相关飞书文档：\n" + "\n".join(lines)
