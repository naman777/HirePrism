from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFINITIONS_DIR = Path("metrics/definitions")


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    label: str
    description: str
    sql: str
    version: str
    owner: str
    tags: list[str]
    category: str  # derived from the source YAML filename (stem)

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags


class MetricRegistry:
    """In-memory catalog of all metric definitions loaded from YAML files."""

    def __init__(self) -> None:
        self._metrics: dict[str, MetricDefinition] = {}

    # ── Loading ──────────────────────────────────────────────────────────────

    def load_directory(self, path: Path = DEFINITIONS_DIR) -> None:
        """Load every *.yaml file in *path* into the registry."""
        for yaml_file in sorted(path.glob("*.yaml")):
            self._load_file(yaml_file)

    def _load_file(self, yaml_file: Path) -> None:
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        category = yaml_file.stem
        for item in raw.get("metrics", []):
            defn = _parse_definition(item, category)
            if defn.name in self._metrics:
                raise ValueError(
                    f"Duplicate metric name '{defn.name}' "
                    f"(first seen in '{self._metrics[defn.name].category}', "
                    f"conflict in '{category}')"
                )
            self._metrics[defn.name] = defn

    # ── Querying ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> MetricDefinition:
        if name not in self._metrics:
            available = ", ".join(sorted(self._metrics))
            raise KeyError(f"Metric '{name}' not found. Available: {available}")
        return self._metrics[name]

    def all(self) -> list[MetricDefinition]:
        return list(self._metrics.values())

    def by_tag(self, tag: str) -> list[MetricDefinition]:
        return [m for m in self._metrics.values() if m.has_tag(tag)]

    def by_category(self, category: str) -> list[MetricDefinition]:
        return [m for m in self._metrics.values() if m.category == category]

    def names(self) -> list[str]:
        return sorted(self._metrics)

    def __len__(self) -> int:
        return len(self._metrics)

    def __contains__(self, name: str) -> bool:
        return name in self._metrics


def _parse_definition(item: dict[str, Any], category: str) -> MetricDefinition:
    return MetricDefinition(
        name=item["name"],
        label=item["label"],
        description=item["description"],
        sql=item["sql"].strip(),
        version=str(item.get("version", "1.0")),
        owner=str(item.get("owner", "")),
        tags=list(item.get("tags", [])),
        category=category,
    )


def load_registry(path: Path = DEFINITIONS_DIR) -> MetricRegistry:
    """Convenience factory: load and return a fully populated registry."""
    registry = MetricRegistry()
    registry.load_directory(path)
    return registry
