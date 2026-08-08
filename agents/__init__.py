"""
🤖 Agents 模块入口
"""
from agents.base import Agent
from agents.showrunner import Showrunner
from agents.world_architect import WorldArchitect
from agents.character_designer import CharacterDesigner
from agents.character_psychologist import CharacterPsychologist
from agents.scene_writer import SceneWriter
from agents.editor import Editor
from agents.literary_advisor import LiteraryAdvisor
from agents.continuity import ContinuityKeeper
from agents.title_designer import TitleDesigner
from agents.hooker import Hooker
from agents.climax_designer import ClimaxDesigner
from agents.ollama_client import OllamaClient
from agents.llm_client import LLMClient, init_client as init_llm_client
from agents.knowledge import KnowledgeStore, create_knowledge_store

from agents.style_polisher import StylePolisher, create_style_polisher, STYLE_REGISTRY, list_styles
from agents.worklog import WorkLog
from agents.coordinator import BatchCoordinator
from agents.web_search import (
    WebSearchProvider, SearchResult,
    DoubaoSearchProvider, BochaSearchProvider, MockSearchProvider,
    get_search_provider,
)
from agents.topic_researcher import TopicResearcher, DEFAULT_TOPICS
from agents.innovator import Innovator


def get_ollama_client(**kwargs) -> OllamaClient:
    """懒加载 OllamaClient 实例。

    原 __init__.py 在模块导入时就实例化 OllamaClient（可能尝试连接本地 Ollama），
    即使用 LLM 后端时也付出代价。改为按需创建。
    """
    return OllamaClient(**kwargs)


__all__ = [
    "Agent",
    "Showrunner",
    "WorldArchitect",
    "CharacterDesigner",
    "CharacterPsychologist",
    "SceneWriter",
    "Editor",
    "LiteraryAdvisor",
    "ContinuityKeeper",
    "TitleDesigner",
    "Hooker",
    "ClimaxDesigner",
    "OllamaClient", "get_ollama_client",
    "LLMClient", "init_llm_client",
    "KnowledgeStore", "create_knowledge_store",
    "StylePolisher", "create_style_polisher", "STYLE_REGISTRY", "list_styles",
    "WorkLog",
    "BatchCoordinator",
    "WebSearchProvider", "SearchResult",
    "DoubaoSearchProvider", "BochaSearchProvider", "MockSearchProvider",
    "get_search_provider",
    "TopicResearcher", "DEFAULT_TOPICS",
    "Innovator",
]
