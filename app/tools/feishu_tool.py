"""飞书文档工具（真实数据源：知识库 wiki 节点 → docx 正文）

对接链路（对应简历 M4 里程碑）：
1. app_id/app_secret 换取 tenant_access_token（模块级缓存，提前 5 分钟刷新，避免每轮重复换票）
2. 配置的 wiki token 经 /wiki/v2/spaces/get_node 换取真实 docx document_id（用户文档在知识库，链接需换票）
3. /docx/v1/documents/{id}/raw_content 拉取正文，按关键词与时间范围过滤
"""
import time
from datetime import datetime

import httpx
from langchain_core.tools import tool

from app.config import get_settings

FEISHU_API = "https://open.feishu.cn/open-apis"
CONTENT_LIMIT = 300  # 单篇正文截断长度，控制 token 消耗

# tenant_access_token 模块级缓存：有效期内复用，降低换票请求次数
_token_cache: dict = {"token": "", "expires_at": 0.0}


async def _get_tenant_token() -> str:
    settings = get_settings()
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        )
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg')}")
    _token_cache["token"] = data["tenant_access_token"]
    # 提前 5 分钟过期，留出时钟偏差余量
    _token_cache["expires_at"] = time.time() + data.get("expire", 7200) - 300
    return _token_cache["token"]


@tool
async def fetch_feishu_docs(keyword: str, since: str = "", until: str = "") -> str:
    """按关键词检索团队飞书知识库文档（设计文档、评审记录、会议纪要等）。

    Args:
        keyword: 关键词，如 "支付" 或 "评审"；传空字符串返回全部近期文档
        since: 起始日期，格式 YYYY-MM-DD，可传空
        until: 截止日期，格式 YYYY-MM-DD，可传空
    """
    settings = get_settings()
    wiki_tokens = [t.strip() for t in settings.feishu_doc_tokens.split(",") if t.strip()]
    if not wiki_tokens:
        return "未配置飞书文档列表（FEISHU_DOC_TOKENS），无法检索文档。"

    tenant_token = await _get_tenant_token()
    headers = {"Authorization": f"Bearer {tenant_token}"}
    docs: list[dict] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=15) as client:
        for wiki_token in wiki_tokens:
            try:
                # 1) wiki token 换真实文档节点
                node_resp = await client.get(
                    f"{FEISHU_API}/wiki/v2/spaces/get_node",
                    headers=headers,
                    params={"token": wiki_token},
                )
                node_data = node_resp.json()
                if node_data.get("code") != 0:
                    errors.append(f"{wiki_token[:8]}… 节点解析失败: {node_data.get('msg')}")
                    continue
                node = node_data["data"]["node"]

                # 2) 拉取 docx 正文
                raw_resp = await client.get(
                    f"{FEISHU_API}/docx/v1/documents/{node['obj_token']}/raw_content",
                    headers=headers,
                )
                raw_data = raw_resp.json()
                if raw_data.get("code") != 0:
                    errors.append(
                        f"《{node.get('title', '未知文档')}》读取失败({raw_data.get('code')}): "
                        f"{raw_data.get('msg')}（常见原因：未把应用添加为文档协作者/知识库成员）"
                    )
                    continue

                docs.append({
                    "title": node.get("title", "无标题"),
                    "updated_at": datetime.fromtimestamp(node.get("obj_edit_time", 0)).strftime("%Y-%m-%d"),
                    "content": (raw_data.get("data", {}).get("content") or "")[:CONTENT_LIMIT],
                })
            except Exception as exc:  # 单篇失败不阻塞其余文档
                errors.append(f"{wiki_token[:8]}… 请求异常: {exc}")

    # 过滤逻辑与关键词、时间范围保持一致（日期字符串可直接比较）
    hits = [
        d for d in docs
        if (not keyword or keyword in d["title"] or keyword in d["content"])
        and (not since or d["updated_at"] >= since)
        and (not until or d["updated_at"] <= until)
    ]

    if not hits:
        report = f"未找到与「{keyword}」相关的文档。"
    else:
        lines = [f"- [{d['updated_at']}] 《{d['title']}》：{d['content']}" for d in hits]
        report = f"检索到 {len(hits)} 篇相关飞书文档：\n" + "\n".join(lines)

    if errors:
        report += "\n另有部分文档读取失败：" + "；".join(errors)
    return report
