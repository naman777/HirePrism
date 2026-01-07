from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.metrics.loader import MetricDefinition, MetricRegistry, load_registry
from src.modeling.build_tables import DB_PATH, connect

log = logging.getLogger(__name__)


class MetricExecutor:
    """Runs named metrics from a MetricRegistry against the DuckDB database."""

    def __init__(
        self,
        db_path: Path = DB_PATH,
        registry: MetricRegistry | None = None,
    ) -> None:
        self.db_path = db_path
        self._registry = registry or load_registry()

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self, name: str) -> pd.DataFrame:
        """Execute a metric by name and return a DataFrame."""
        metric = self._registry.get(name)
        return self._execute(metric)

    def run_definition(self, metric: MetricDefinition) -> pd.DataFrame:
        """Execute a MetricDefinition directly."""
        return self._execute(metric)

    def run_all(self) -> dict[str, pd.DataFrame]:
        """Run every registered metric; return {name: DataFrame}."""
        results: dict[str, pd.DataFrame] = {}
        for metric in self._registry.all():
            try:
                results[metric.name] = self._execute(metric)
            except Exception as exc:
                log.error("Metric '%s' failed: %s", metric.name, exc)
                results[metric.name] = pd.DataFrame()
        return results

    def run_by_tag(self, tag: str) -> dict[str, pd.DataFrame]:
        """Run all metrics that carry a given tag."""
        results: dict[str, pd.DataFrame] = {}
        for metric in self._registry.by_tag(tag):
            results[metric.name] = self._execute(metric)
        return results

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    # ── Internal ─────────────────────────────────────────────────────────────

    def _execute(self, metric: MetricDefinition) -> pd.DataFrame:
        con = connect(self.db_path, read_only=True)
        try:
            df = con.execute(metric.sql).df()
            log.debug("Metric '%s' → %d rows", metric.name, len(df))
            return df
        finally:
            con.close()


def main() -> None:
    """Print a summary of all metrics and spot-check two of them."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    executor = MetricExecutor()
    registry = executor.registry

    log.info("Loaded %d metrics across %d categories:", len(registry),
             len({m.category for m in registry.all()}))
    for m in registry.all():
        log.info("  [%s] %s — %s", m.category, m.name, m.label)

    log.info("\n── high_package_rate ──")
    df = executor.run("high_package_rate")
    print(df.to_string(index=False))

    log.info("\n── role_family_distribution ──")
    df = executor.run("role_family_distribution")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
