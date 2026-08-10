"""Application context: wires concrete infrastructure into the domain
interfaces. Tests substitute fakes via the constructor."""

from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.business.comparison import MetricComparisonService
from app.business.routing import ChangeRouter
from app.business.validation import ChangeValidator
from app.config.loader import get_variable_registry
from app.config.settings import Settings, get_settings
from app.domain.interfaces import (
    LLMInterpreter,
    MacroModelRunner,
    TaxModelRunner,
    TaxToFairAdapter,
)
from app.domain.registry import VariableRegistry


@dataclass
class AppContext:
    settings: Settings
    registry: VariableRegistry
    validator: ChangeValidator
    router: ChangeRouter
    comparison: MetricComparisonService
    fair_runner: MacroModelRunner
    tax_runner: TaxModelRunner
    tax_adapter: TaxToFairAdapter
    interpreter: LLMInterpreter
    session_factory: Callable[[], Session]


def build_default_context() -> AppContext:
    from app.infrastructure.adapters.tax_to_fair import ConfiguredTaxToFairAdapter
    from app.infrastructure.fair.service import FairModelRunner
    from app.infrastructure.llm.client import AnthropicInterpreter
    from app.infrastructure.persistence.db import open_session
    from app.infrastructure.taxcalc.runner import TaxCalculatorRunner

    settings = get_settings()
    registry = get_variable_registry()
    return AppContext(
        settings=settings,
        registry=registry,
        validator=ChangeValidator(registry),
        router=ChangeRouter(registry),
        comparison=MetricComparisonService(),
        fair_runner=FairModelRunner(settings),
        tax_runner=TaxCalculatorRunner(settings),
        tax_adapter=ConfiguredTaxToFairAdapter(),
        interpreter=AnthropicInterpreter(settings),
        session_factory=open_session,
    )
