from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ProviderAdapter
from app.providers.custom_http import CustomHTTPAdapter
from app.providers.codex import CodexAdapter
from app.providers.deepseek import DeepSeekAdapter
from app.providers.firecrawl import FirecrawlAdapter
from app.providers.icons import PROVIDER_ICONS
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter

ADAPTERS: dict[str, type[ProviderAdapter]] = {
    FirecrawlAdapter.id: FirecrawlAdapter,
    CodexAdapter.id: CodexAdapter,
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
    return [
        {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description,
            "metrics": cls.metric_names,
            "alert_metrics": cls.alert_metrics,
            "icon": PROVIDER_ICONS.get(cls.id),
            "analytics": cls.analytics,
        }
        for cls in ADAPTERS.values()
    ]
