"""Model module - wraps LangChain Ollama chat model with tool binding and fallback."""

from querygraph_agent.model.ollama_client import OllamaClient

__all__ = ["OllamaClient"]
