from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class Metric:
    label: str
    value: float | int | str | bool | None
    unit: str | None = None
    maximum: float | int | None = None

@dataclass(slots=True)
class ProviderUsage:
    status: str
    summary: str
    metrics: list[Metric]
    raw: dict[str, Any] = field(default_factory=dict)

class ProviderAdapter(ABC):
    id: str
    name: str
    description: str
    default_base_url: str
    metric_names: list[str]

    def __init__(self, api_key: str, base_url: str | None = None, timeout: float = 20.0, extra: dict[str, Any] | None = None):
        self.api_key = api_key
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.timeout = timeout
        self.extra = extra or {}

    @abstractmethod
    async def fetch_usage(self) -> ProviderUsage:
        raise NotImplementedError
