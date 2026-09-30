"""GitHub 提交记录拉取工具（真实数据源）"""
import httpx
from langchain_core.tools import tool

from app.config import get_settings

GITHUB_API = "https://api.github.com"


@tool
async def fetch_github_commits(repo: str, since: str, until: str) -> str:
    """拉取指定 GitHub 仓库在时间范围内的提交记录摘要。

    Args:
        repo: 仓库全名，如 "octocat/Hello-World"
        since: 起始时间，ISO8601 格式，如 2026-09-22T00:00:00Z
        until: 截止时间，ISO8601 格式
    """
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    url = f"{GITHUB_API}/repos/{repo}/commits"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params={"since": since, "until": until, "per_page": 100})
        resp.raise_for_status()
        commits = resp.json()

    if not commits:
        return f"仓库 {repo} 在 {since} ~ {until} 时间范围内没有提交记录。"

    # 压缩为 LLM 友好的一行式摘要，控制 token 消耗
    lines = [
        f"- {c['sha'][:7]} [{c['commit']['author']['name']}] {c['commit']['message'].splitlines()[0]}"
        for c in commits
    ]
    return f"仓库 {repo} 在 {since} ~ {until} 共 {len(lines)} 条提交：\n" + "\n".join(lines)
