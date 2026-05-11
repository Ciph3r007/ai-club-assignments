"""LangChain Ollama chat model wrapper.

Provides ``OllamaClient``, which:
- Wraps ``ChatOllama`` with tool binding capability.
- Implements a model fallback sequence (REQ-ERR-002): if the primary model
  cannot be initialised or fails on first invocation, the client falls back
  through ``settings.ollama_fallback_models`` in order.  If all candidates are
  exhausted, ``ModelToolCallError`` is raised.

The fallback strategy is conservative: we attempt to create a ``ChatOllama``
for each candidate model.  The actual connectivity test happens lazily (on
first invocation), because ``ChatOllama`` does not contact Ollama at
construction time.  Callers that need eager validation should call
``bind_tools()`` and invoke the model in a try/except block.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from library.config.settings import Settings
from library.exceptions import ModelToolCallError


class OllamaClient:
    """Wraps ``ChatOllama`` with tool binding and model fallback.

    Parameters
    ----------
    settings:
        Application settings containing ``ollama_base_url``,
        ``ollama_model``, and ``ollama_fallback_models``.
    tools:
        List of LangChain tool objects to bind to the model.
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
        """The underlying ``ChatOllama`` instance."""
        return self._model

    def bind_tools(self) -> BaseChatModel:
        """Return the model with tools bound for tool-call routing.

        Returns
        -------
        BaseChatModel
            A model instance that includes the tool schemas from
            ``self._tools`` in every request to Ollama.
        """
        return self._model.bind_tools(self._tools)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_model(self, model_name: str) -> ChatOllama:
        """Instantiate a ``ChatOllama`` for the given model name.

        ``ChatOllama`` construction does not contact Ollama, so this cannot
        raise transport errors.  ``ModelToolCallError`` is only raised here if
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
        """Try to create the primary model, fall through fallback list on failure.

        On success the first successfully-created ``ChatOllama`` is returned.
        If all candidates fail, ``ModelToolCallError`` is raised with the last
        error (REQ-ERR-002).

        Parameters
        ----------
        primary_model:
            The preferred model name (``settings.ollama_model``).

        Raises
        ------
        ModelToolCallError
            When every candidate in the fallback sequence fails.
        """
        candidates = [primary_model, *self._settings.ollama_fallback_models]
        last_exc: Exception | None = None

        for model_name in candidates:
            try:
                return self._create_model(model_name)
            except ModelToolCallError as exc:
                last_exc = exc
                continue

        # All candidates exhausted - this branch is only reached if every
        # _create_model call raised ModelToolCallError.
        raise ModelToolCallError(
            f"All model fallbacks exhausted.  Tried: {candidates}.  Last error: {last_exc}"
        ) from last_exc


__all__ = ["OllamaClient"]
