"""Fail-fast YAML config loaders for the variable registry, metric catalog,
and Tax-to-Fair mapping table."""

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from app.config.settings import get_settings
from app.domain.enums import ChangeType, ModelRoute
from app.domain.errors import ConfigurationError
from app.domain.registry import VariableRegistry, VariableSpec

_VALID_PARAM_KINDS = {"scalar", "mars_vector", "composite"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigurationError(message)


def load_variable_registry(path: Path | None = None) -> VariableRegistry:
    path = path or get_settings().config_dir / "economic_variables.yaml"
    _require(path.exists(), f"Variable registry not found: {path}")
    raw = yaml.safe_load(path.read_text())
    _require(isinstance(raw, dict) and isinstance(raw.get("variables"), list),
             f"{path}: expected top-level 'variables' list")

    variables: dict[str, VariableSpec] = {}
    for entry in raw["variables"]:
        _require(isinstance(entry, dict), f"{path}: variable entry must be a mapping")
        vid = entry.get("id")
        _require(bool(vid), f"{path}: variable entry missing 'id'")
        _require(vid not in variables, f"{path}: duplicate variable id {vid!r}")
        try:
            route = ModelRoute.DIRECT_FAIR if entry["model"] == "FAIR" else ModelRoute.TAX_CALCULATOR
            _require(entry["model"] in ("FAIR", "TAX_CALCULATOR"),
                     f"{vid}: unknown model {entry['model']!r}")
            allowed = frozenset(ChangeType(ct) for ct in entry["allowed_change_types"])
            _require(len(allowed) > 0, f"{vid}: empty allowed_change_types")
            spec = VariableSpec(
                id=vid,
                label=entry["label"],
                model_route=route,
                unit=entry["unit"],
                allowed_change_types=allowed,
                description=entry.get("description", ""),
                fair_variable=entry.get("fair_variable"),
                requires_exogenous=bool(entry.get("requires_exogenous", False)),
                taxcalc_param=entry.get("taxcalc_param"),
                param_kind=entry.get("param_kind"),
                reform_year=entry.get("reform_year"),
                composite_of=tuple(entry.get("composite_of", ())),
                min_value=Decimal(str(entry["min_value"])) if "min_value" in entry else None,
                max_value=Decimal(str(entry["max_value"])) if "max_value" in entry else None,
            )
        except KeyError as exc:
            raise ConfigurationError(f"{path}: variable {vid!r} missing required key {exc}") from None
        except ValueError as exc:
            raise ConfigurationError(f"{path}: variable {vid!r}: {exc}") from None

        if spec.model_route is ModelRoute.DIRECT_FAIR:
            _require(bool(spec.fair_variable), f"{vid}: FAIR variable requires 'fair_variable'")
            _require(spec.fair_variable == spec.fair_variable.upper(),
                     f"{vid}: fair_variable must be UPPERCASE")
        else:
            _require(bool(spec.taxcalc_param), f"{vid}: TAX_CALCULATOR variable requires 'taxcalc_param'")
            _require(spec.param_kind in _VALID_PARAM_KINDS,
                     f"{vid}: param_kind must be one of {_VALID_PARAM_KINDS}")
            _require(spec.reform_year is not None, f"{vid}: TAX_CALCULATOR variable requires 'reform_year'")
            if spec.param_kind == "composite":
                _require(len(spec.composite_of) > 0, f"{vid}: composite requires 'composite_of'")

        variables[vid] = spec

    return VariableRegistry(variables=variables)


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    label: str
    unit: str


def load_metric_catalog(path: Path | None = None) -> dict[str, MetricSpec]:
    path = path or get_settings().config_dir / "metrics.yaml"
    _require(path.exists(), f"Metric catalog not found: {path}")
    raw = yaml.safe_load(path.read_text())
    _require(isinstance(raw, dict) and isinstance(raw.get("metrics"), list),
             f"{path}: expected top-level 'metrics' list")
    catalog: dict[str, MetricSpec] = {}
    for entry in raw["metrics"]:
        try:
            spec = MetricSpec(name=entry["name"], label=entry["label"], unit=entry["unit"])
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"{path}: bad metric entry {entry!r}: {exc}") from None
        _require(spec.name not in catalog, f"{path}: duplicate metric {spec.name!r}")
        catalog[spec.name] = spec
    _require(len(catalog) > 0, f"{path}: no metrics defined")
    return catalog


@dataclass(frozen=True, slots=True)
class MappingSpec:
    id: str
    method: str
    source_variables: frozenset[str]
    target_fair_variable: str
    fair_change_type: ChangeType
    allocation: str
    notes: str = ""


@dataclass(frozen=True)
class MappingTable:
    mappings: tuple[MappingSpec, ...] = field(default_factory=tuple)

    def find_for_variable(self, variable_id: str) -> MappingSpec | None:
        for m in self.mappings:
            if variable_id in m.source_variables:
                return m
        return None


_VALID_METHODS = {"EFFECTIVE_RATE_DELTA", "STATUTORY_RATE_PASSTHROUGH"}


def load_mapping_table(path: Path | None = None) -> MappingTable:
    path = path or get_settings().config_dir / "tax_to_fair_mapping.yaml"
    _require(path.exists(), f"Tax-to-Fair mapping table not found: {path}")
    raw = yaml.safe_load(path.read_text())
    _require(isinstance(raw, dict) and isinstance(raw.get("mappings"), list),
             f"{path}: expected top-level 'mappings' list")
    specs: list[MappingSpec] = []
    seen_sources: set[str] = set()
    for entry in raw["mappings"]:
        try:
            spec = MappingSpec(
                id=entry["id"],
                method=entry["method"],
                source_variables=frozenset(entry["source_variables"]),
                target_fair_variable=entry["target_fair_variable"],
                fair_change_type=ChangeType(entry["fair_change_type"]),
                allocation=entry["allocation"],
                notes=entry.get("notes", ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"{path}: bad mapping entry {entry!r}: {exc}") from None
        _require(spec.method in _VALID_METHODS,
                 f"{path}: mapping {spec.id!r}: unknown method {spec.method!r}")
        _require(spec.allocation == "CONSTANT",
                 f"{path}: mapping {spec.id!r}: only CONSTANT allocation is implemented")
        overlap = spec.source_variables & seen_sources
        _require(not overlap, f"{path}: variables {sorted(overlap)} appear in multiple mappings")
        seen_sources |= spec.source_variables
        specs.append(spec)
    return MappingTable(mappings=tuple(specs))


@lru_cache
def get_variable_registry() -> VariableRegistry:
    return load_variable_registry()


@lru_cache
def get_metric_catalog() -> dict[str, MetricSpec]:
    return load_metric_catalog()


@lru_cache
def get_mapping_table() -> MappingTable:
    return load_mapping_table()
