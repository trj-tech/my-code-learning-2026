"""API 请求/响应模型"""
from pydantic import BaseModel, Field


class GenerateReportRequest(BaseModel):
    repo: str = Field(description="GitHub 仓库全名，如 octocat/Hello-World")
    since: str = Field(description="起始时间 ISO8601，如 2026-09-22T00:00:00Z")
    until: str = Field(description="截止时间 ISO8601，如 2026-09-30T23:59:59Z")
    team: str = Field(default="default", description="团队标识（记忆隔离键）")


class RunStats(BaseModel):
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    iterations: int
    memory_hit: bool


class GenerateReportResponse(BaseModel):
    run_id: str
    report: str
    stats: RunStats
