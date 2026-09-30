"""Agent 记忆层

- 短期记忆：LangGraph checkpointer 保存单次任务的多轮工具调用上下文，
  支持 graph 中断恢复。生产环境把 MemorySaver 换成 langgraph-checkpoint-redis
  的 RedisSaver 即可持久化，接口不变。
- 长期记忆：Redis 缓存团队上一期周报全文。下次生成时注入 prompt 作为格式与
  内容延续性参考，命中缓存可跳过向量检索与额外归纳调用——这是"重复调用
  成本降低"的核心手段。
- 降级策略：Redis 不可用时静默降级为无缓存模式，不影响主流程。
"""
import logging

import redis.asyncio as aioredis
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)

LTM_TTL_SECONDS = 14 * 24 * 3600  # 缓存两周，覆盖周报生成的最长间隔


def build_checkpointer() -> MemorySaver:
    """短期记忆。切换 RedisSaver 只需改这一处"""
    return MemorySaver()


class LongTermMemory:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis | None:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    get_settings().redis_url, decode_responses=True
                )
                await self._redis.ping()
            except Exception as e:  # 连接失败降级为无缓存
                logger.warning("Redis 不可用，长期记忆降级为无缓存模式: %s", e)
                self._redis = None
                return None
        return self._redis

    @staticmethod
    def _key(team: str) -> str:
        return f"ltm:last_report:{team}"

    async def get_last_report(self, team: str) -> str | None:
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            return await redis.get(self._key(team))
        except Exception as e:
            logger.warning("读取长期记忆失败: %s", e)
            return None

    async def save_last_report(self, team: str, report: str) -> None:
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            await redis.set(self._key(team), report, ex=LTM_TTL_SECONDS)
        except Exception as e:
            logger.warning("写入长期记忆失败: %s", e)
