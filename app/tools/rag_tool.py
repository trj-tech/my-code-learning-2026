"""历史周报向量检索工具（Chroma 持久化）

作用：生成新周报前检索语义相近的历史周报作为格式与内容延续性参考，
避免每次都让大模型重新归纳格式（降低 token 成本、保证团队周报风格一致）。
"""
import chromadb
from langchain_core.tools import tool

from app.config import get_settings

COLLECTION = "weekly_reports"
_client: chromadb.api.ClientAPI | None = None


def _get_collection() -> chromadb.api.Collection:
    global _client
    if _client is None:
        settings = get_settings()
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client.get_or_create_collection(COLLECTION)


async def save_report_to_index(report: str, metadata: dict) -> None:
    """业务层调用：把生成的周报写入向量库，供后续检索（不属于 Agent 工具）"""
    col = _get_collection()
    col.add(ids=[metadata["run_id"]], documents=[report], metadatas=[metadata])


@tool
async def search_similar_reports(query: str) -> str:
    """检索语义最相近的历史团队周报，作为本周周报的格式与内容延续性参考。

    Args:
        query: 检索内容，如 "本周支付模块进展 周报"
    """
    col = _get_collection()
    if col.count() == 0:
        return "向量库中暂无历史周报，本次请自行按标准结构生成。"

    res = col.query(query_texts=[query], n_results=min(2, col.count()))
    parts = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        parts.append(f"=== 历史周报（{meta.get('period', '未知周期')}）===\n{doc}")
    return "检索到以下历史周报供参考格式：\n" + "\n\n".join(parts)
