"""Model module - wraps LangChain Ollama chat model with tool binding and fallback."""

from library.model.ollama_client import OllamaClient

__all__ = ["OllamaClient"]
