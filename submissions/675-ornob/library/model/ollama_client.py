"""LangChain Ollama chat model wrapper.

Provides `OllamaClient`, which wraps `ChatOllama` with tool binding and a
model fallback sequence. If the primary model cannot be initialised, the
client falls back through `settings.ollama_fallback_models` in order. If all
candidates are exhausted, `ModelToolCallError` is raised.

The fallback strategy is lazy: `ChatOllama` does not contact Ollama at
construction time, so connectivity errors only surface on first invocation.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from library.config.settings import Settings
from library.exceptions import ModelToolCallError


class OllamaClient:
    """Wraps `ChatOllama` with tool binding and model fallback.

    Args:
        settings: Application settings containing `ollama_base_url`,
            `ollama_model`, and `ollama_fallback_models`.
        tools: LangChain tool objects to bind to the model.
    """

    def __init__(self, settings: Settings, tools: list[Any]) -> None:
        self._settings = settings
        self._tools = tools
        self._model = self._create_model_with_fallback(settings.ollama_model)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def model(self) -> ChatOllama:
        """The underlying `ChatOllama` instance."""
        return self._model

    def bind_tools(self) -> BaseChatModel:
        """Return the model with tools bound for tool-call routing.

        Returns:
            BaseChatModel: A model instance that includes the tool schemas
                from `self._tools` in every request to Ollama.
        """
        return self._model.bind_tools(self._tools)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_model(self, model_name: str) -> ChatOllama:
        """Instantiate a `ChatOllama` for the given model name.

        `ChatOllama` construction does not contact Ollama, so this cannot
        raise transport errors.  `ModelToolCallError` is only raised here if
        something goes wrong at the Python object creation level.
        """
        try:
            return ChatOllama(
                model=model_name,
                base_url=self._settings.ollama_base_url,
            )
        except Exception as exc:
            raise ModelToolCallError(
                f"Failed to create ChatOllama for model {model_name!r}: {exc}"
            ) from exc

    def _create_model_with_fallback(self, primary_model: str) -> ChatOllama:
        """Try to create the primary model, fall through the fallback list on failure.

        Returns the first successfully created `ChatOllama`.

        Args:
            primary_model: The preferred model name (from `settings.ollama_model`).

        Raises:
            ModelToolCallError: When every candidate in the fallback sequence fails.
        """
        candidates = [primary_model, *self._settings.ollama_fallback_models]
        errors: list[ModelToolCallError] = []

        for model_name in candidates:
            try:
                return self._create_model(model_name)
            except ModelToolCallError as exc:
                errors.append(exc)

        raise ModelToolCallError(
            f"All model fallbacks exhausted. Tried: {candidates}. Last error: {errors[-1]}"
        ) from errors[-1]


__all__ = ["OllamaClient"]
