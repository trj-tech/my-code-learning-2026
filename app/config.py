"""全局配置：统一从 .env 读取，业务代码通过 get_settings() 获取单例"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 大模型（DeepSeek OpenAI 兼容接口）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # GitHub 数据源
    github_token: str = ""

    # Redis（长期记忆缓存）
    redis_url: str = "redis://localhost:6379/0"

    # Chroma 向量库持久化目录
    chroma_dir: str = "./data/chroma"

    # Agent 守卫参数：最大工具调用轮次，防止死循环
    agent_max_iterations: int = 12
    tool_retry_times: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
