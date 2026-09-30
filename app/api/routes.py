"""REST API 路由"""
from fastapi import APIRouter, HTTPException

from app.models.schemas import GenerateReportRequest, GenerateReportResponse
from app.services.metrics import metrics
from app.services.report_service import generate_report

router = APIRouter()


@router.post("/reports/generate", response_model=GenerateReportResponse)
async def create_report(req: GenerateReportRequest):
    """触发一次团队周报生成（Agent 全流程：拉数据 → 聚合 → 输出）"""
    try:
        return await generate_report(req)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"周报生成失败: {e}")


@router.get("/metrics")
async def get_metrics():
    """运行指标：工具调用成功率、最近任务耗时与 token 消耗"""
    return metrics.snapshot()


@router.get("/health")
async def health():
    return {"status": "ok"}
