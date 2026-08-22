"""Data source registry and lookup."""

from __future__ import annotations

from app.datasources.base import DataSource
from app.datasources.hermes import HermesDataSource

DATA_SOURCES: dict[str, type[DataSource]] = {
    HermesDataSource.id: HermesDataSource,
}


def get_data_source(kind: str) -> type[DataSource]:
    try:
        return DATA_SOURCES[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported data source: {kind}") from exc


def list_data_sources() -> list[dict]:
    return [
        {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description,
            "metrics": cls.metric_names,
        }
        for cls in DATA_SOURCES.values()
    ]
