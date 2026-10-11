"""Public model transport factory; optional HTTP dependencies load on use."""

from .provider_adapters import (
    AnthropicMessagesProvider,
    ChatCompletionsProvider,
    OpenAIResponsesProvider,
)
from .providers import provider_catalog

__all__ = [
    "AnthropicMessagesProvider",
    "ChatCompletionsProvider",
    "OpenAIResponsesProvider",
    "create_provider",
    "provider_catalog",
]


def create_provider(config, client=None):
    """Select a wire protocol; provider profiles control compatible parameters."""
    protocols = {
        "chat_completions": ChatCompletionsProvider,
        "responses": OpenAIResponsesProvider,
        "anthropic_messages": AnthropicMessagesProvider,
    }
    protocol = getattr(config, "protocol", "chat_completions")
    if protocol not in protocols:
        raise ValueError("Unsupported model provider protocol")
    return protocols[protocol](config, client=client)
