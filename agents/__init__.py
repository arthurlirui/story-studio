"""
🤖 Agents 模块入口
"""
from agents.base import Agent
from agents.showrunner import Showrunner
from agents.world_architect import WorldArchitect
from agents.character_designer import CharacterDesigner
from agents.scene_writer import SceneWriter
from agents.editor import Editor
from agents.literary_advisor import LiteraryAdvisor
from agents.continuity import ContinuityKeeper
from agents.title_designer import TitleDesigner
from agents.hooker import Hooker
from agents.climax_designer import ClimaxDesigner
from agents.ollama_client import OllamaClient, client as ollama_client
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

__all__ = [
    "Agent",
    "Showrunner",
    "WorldArchitect",
    "CharacterDesigner",
    "SceneWriter",
    "Editor",
    "LiteraryAdvisor",
    "ContinuityKeeper",
    "TitleDesigner",
    "Hooker",
    "ClimaxDesigner",
    "OllamaClient", "ollama_client",
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
