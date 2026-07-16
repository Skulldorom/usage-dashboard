from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ProviderAdapter
from app.providers.custom_http import CustomHTTPAdapter
from app.providers.deepseek import DeepSeekAdapter
from app.providers.firecrawl import FirecrawlAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter

ADAPTERS: dict[str, type[ProviderAdapter]] = {
    FirecrawlAdapter.id: FirecrawlAdapter,
    DeepSeekAdapter.id: DeepSeekAdapter,
    OpenAIAdapter.id: OpenAIAdapter,
    AnthropicAdapter.id: AnthropicAdapter,
    OpenRouterAdapter.id: OpenRouterAdapter,
    CustomHTTPAdapter.id: CustomHTTPAdapter,
}

def get_adapter_class(provider: str) -> type[ProviderAdapter]:
    try:
        return ADAPTERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {provider}") from exc

def list_providers() -> list[dict]:
    return [{"id": cls.id, "name": cls.name, "description": cls.description, "metrics": cls.metric_names} for cls in ADAPTERS.values()]
