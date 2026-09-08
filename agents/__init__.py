"""
🤖 Agents 模块入口

子包结构：
  agents/creative/   创作线 Agent（showrunner / scene_writer / editor ...）
  agents/research/   调研线 Agent（topic_researcher / innovator / trending_words）
  agents/tools/      工具 Agent（web_search / style_polisher / multi_polisher / text_cleaner）
  agents/ 顶层       基础设施（base / llm_client / knowledge / worklog / coordinator / utils）
"""
from agents.base import Agent
from agents.creative import (
    Showrunner, WorldArchitect, CharacterDesigner, CharacterPsychologist,
    SceneWriter, Editor, LiteraryAdvisor, ContinuityKeeper,
    TitleDesigner, Hooker, ClimaxDesigner,
)
from agents.research import (
    TopicResearcher, DEFAULT_TOPICS, Innovator, TrendingWords,
)
from agents.research.trending_words import DEFAULT_QUERIES as DEFAULT_TRENDING_QUERIES

from agents.tools import (
    StylePolisher, create_style_polisher, STYLE_REGISTRY, list_styles,
    WebSearchProvider, SearchResult,
    DoubaoSearchProvider, BochaSearchProvider, MockSearchProvider,
    get_search_provider,
)

from agents.ollama_client import OllamaClient
from agents.llm_client import LLMClient, init_client as init_llm_client
from agents.knowledge import KnowledgeStore, create_knowledge_store
from agents.worklog import WorkLog
from agents.coordinator import BatchCoordinator


def get_ollama_client(**kwargs) -> OllamaClient:
    """懒加载 OllamaClient 实例。

    原 __init__.py 在模块导入时就实例化 OllamaClient（可能尝试连接本地 Ollama），
    即使用 LLM 后端时也付出代价。改为按需创建。
    """
    return OllamaClient(**kwargs)


__all__ = [
    "Agent",
    "Showrunner", "WorldArchitect", "CharacterDesigner", "CharacterPsychologist",
    "SceneWriter", "Editor", "LiteraryAdvisor", "ContinuityKeeper",
    "TitleDesigner", "Hooker", "ClimaxDesigner",
    "TopicResearcher", "DEFAULT_TOPICS", "Innovator",
    "TrendingWords", "DEFAULT_TRENDING_QUERIES",
    "StylePolisher", "create_style_polisher", "STYLE_REGISTRY", "list_styles",
    "WebSearchProvider", "SearchResult",
    "DoubaoSearchProvider", "BochaSearchProvider", "MockSearchProvider",
    "get_search_provider",
    "OllamaClient", "get_ollama_client",
    "LLMClient", "init_llm_client",
    "KnowledgeStore", "create_knowledge_store",
    "WorkLog",
    "BatchCoordinator",
]
