"""
Trader Intelligence System — Unified Brief Schema & Semantic Validator

Production-grade data model for the morning pipeline:
  Canvas → Vision → Structured JSON → Pydantic Validation → Gatekeeper

Validates SMC boundary rules (buy below price, sell above price),
numerai correlation sanity, and provides a full audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────
#  SMC Data Models
# ──────────────────────────────────────────────


class SMCPatterns(BaseModel):
    """Smart Money Concepts patterns extracted from chart vision analysis."""

    order_blocks: Dict[str, List[float]] = Field(
        default_factory=lambda: {"buy": [], "sell": []},
        description="Demand (buy) zones should be below price; supply (sell) zones above.",
    )
    fvg: List[float] = Field(
        default_factory=list,
        description="Fair Value Gaps — price levels where gaps were formed.",
    )
    liquidity_sweeps: List[float] = Field(
        default_factory=list,
        description="Price levels where liquidity was swept above highs or below lows.",
    )
    choch: List[float] = Field(
        default_factory=list,
        description="Change of Character levels — shifts in market structure.",
    )
    bos: List[float] = Field(
        default_factory=list,
        description="Break of Structure levels.",
    )
    support: List[float] = Field(
        default_factory=list,
        description="Key support levels (below current price).",
    )
    resistance: List[float] = Field(
        default_factory=list,
        description="Key resistance levels (above current price).",
    )
    structure: Literal["bullish", "bearish", "neutral"] = "neutral"

    @model_validator(mode="after")
    def verify_smc_boundaries(self, info: Any) -> "SMCPatterns":
        """Catch the semantic inversion bug: buy blocks above price, sell blocks below."""
        ctx = info.context or {}
        current_price = ctx.get("current_price")

        if current_price is None:
            return self

        for level in self.order_blocks.get("buy", []):
            if level > current_price:
                raise ValueError(
                    f"SMC Violation: Buy Order Block {level} is ABOVE "
                    f"current price {current_price}. "
                    "Buy zones must rest below market for retest."
                )

        for level in self.order_blocks.get("sell", []):
            if level < current_price:
                raise ValueError(
                    f"SMC Violation: Sell Order Block {level} is BELOW "
                    f"current price {current_price}. "
                    "Sell zones must sit above market."
                )

        for level in self.support:
            if level > current_price:
                raise ValueError(
                    f"SMC Violation: Support level {level} is ABOVE "
                    f"current price {current_price}."
                )

        for level in self.resistance:
            if level < current_price:
                raise ValueError(
                    f"SMC Violation: Resistance level {level} is BELOW "
                    f"current price {current_price}."
                )

        return self


class AssetAnalysis(BaseModel):
    """Per-asset analysis block."""

    ticker: str
    current_price: float
    source: str = "TradingView DOM anchor"
    screenshot_path: Optional[str] = None
    smc: SMCPatterns


# ──────────────────────────────────────────────
#  Numerai Data Models
# ──────────────────────────────────────────────


class NumeraiSignals(BaseModel):
    """Numerai tournament signals summary."""

    round_number: int = 0
    top_signals: List[str] = Field(default_factory=list, description="Top predicted assets")
    bottom_signals: List[str] = Field(default_factory=list, description="Bottom predicted assets")
    correlation_score: Optional[float] = None

    @field_validator("correlation_score")
    @classmethod
    def validate_correlation(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and abs(v) > 1.0:
            raise ValueError(f"Correlation must be between -1 and 1, got {v}")
        return v


# ──────────────────────────────────────────────
#  Macro Context
# ──────────────────────────────────────────────


class MacroContext(BaseModel):
    """Qualitative macro and geopolitical context."""

    saii_headlines: List[str] = Field(default_factory=list)
    high_impact_events: List[str] = Field(default_factory=list)
    risk_sentiment: Literal["risk_on", "risk_off", "neutral"] = "neutral"


# ──────────────────────────────────────────────
#  Audit Trail
# ──────────────────────────────────────────────


class AuditStep(BaseModel):
    """Single step in the pipeline audit trail."""

    step: str
    passed: bool
    asset: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class GatekeeperDecision(BaseModel):
    """Final gatekeeper validation result."""

    approved: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    audit_trail: List[AuditStep] = Field(default_factory=list)


# ──────────────────────────────────────────────
#  Unified Pipeline Brief
# ──────────────────────────────────────────────


class PipelineBrief(BaseModel):
    """Top-level unified morning brief — the single source of truth."""

    brief_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pipeline_version: str = "1.0"

    assets: List[AssetAnalysis] = Field(default_factory=list)
    numerai: Optional[NumeraiSignals] = None
    macro_context: Optional[MacroContext] = None
    gatekeeper: GatekeeperDecision = Field(default_factory=GatekeeperDecision)

    # ── Serialization helpers ──

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent, exclude_none=True)

    @classmethod
    def from_json(cls, data: str) -> "PipelineBrief":
        return cls.model_validate_json(data)

    def validate_with_price_context(self, current_prices: Dict[str, float]) -> List[str]:
        """
        Re-validate all SMC boundaries with the given price context.
        Returns a list of validation errors (empty = all passed).
        """
        errors: List[str] = []
        for asset in self.assets:
            ticker = asset.ticker
            price = current_prices.get(ticker)
            if price is None:
                errors.append(f"No price anchor for {ticker}, skipping SMC validation")
                continue
            try:
                # Re-validate with price context
                SMCPatterns.model_validate(
                    asset.smc.model_dump(),
                    context={"current_price": price},
                )
            except ValueError as e:
                errors.append(f"{ticker}: {e}")
                asset.smc.structure = "neutral"  # reset on violation
        self.gatekeeper.validation_errors = errors
        self.gatekeeper.approved = len(errors) == 0
        return errors

    def add_audit_step(
        self,
        step: str,
        passed: bool,
        asset: Optional[str] = None,
        model: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        self.gatekeeper.audit_trail.append(
            AuditStep(
                step=step,
                passed=passed,
                asset=asset,
                model=model,
                error=error,
                duration_ms=duration_ms,
            )
        )


# ──────────────────────────────────────────────
#  Quick Self-Test
# ──────────────────────────────────────────────


if __name__ == "__main__":
    print("=== Schema Self-Test ===\n")

    # 1. Build a valid brief
    brief = PipelineBrief(
        brief_id="2026-06-30-test",
        assets=[
            AssetAnalysis(
                ticker="EURUSD",
                current_price=1.1402,
                smc=SMCPatterns(
                    order_blocks={"buy": [1.1350, 1.1280], "sell": [1.1470, 1.1520]},
                    fvg=[1.1320, 1.1470],
                    liquidity_sweeps=[1.1370, 1.1450],
                    choch=[1.1430],
                    bos=[1.1390],
                    support=[1.1350, 1.1280, 1.1220],
                    resistance=[1.1470, 1.1520, 1.1570],
                    structure="bearish",
                ),
            )
        ],
        numerai=NumeraiSignals(
            round_number=240,
            top_signals=["BTCUSD", "SP500"],
            correlation_score=0.042,
        ),
    )

    print("✅ Valid brief created")

    # 2. Test the inversion catch (buy block above price)
    print("\n--- Testing: buy OB above price (should fail) ---")
    try:
        SMCPatterns(
            order_blocks={"buy": [1.1500], "sell": [1.1350]},
            support=[1.1350],
            resistance=[1.1500],
            structure="bearish",
        )
    except ValueError as e:
        print(f"✅ Caught inversion: {e}")

    # 3. Test the inversion catch (sell block below price)
    print("\n--- Testing: sell OB below price (should fail) ---")
    try:
        SMCPatterns(
            order_blocks={"buy": [1.1300], "sell": [1.1250]},
            support=[1.1300],
            resistance=[1.1450],
            structure="bullish",
        )
    except ValueError as e:
        print(f"✅ Caught inversion: {e}")

    # 4. Validate with price context
    print("\n--- Validation with price context ---")
    errors = brief.validate_with_price_context({"EURUSD": 1.1402})
    if not errors:
        print("✅ All SMC boundary checks passed for EURUSD")
    else:
        print(f"Errors: {errors}")

    # 5. Add audit trail
    brief.add_audit_step("canvas_capture", passed=True, asset="EURUSD")
    brief.add_audit_step(
        "vision_analysis",
        passed=True,
        asset="EURUSD",
        model="ministral-14b-latest",
        duration_ms=3500,
    )
    brief.add_audit_step(
        "numerai_signals",
        passed=False,
        error="data not yet downloaded",
    )

    print("\n=== Final Brief JSON ===")
    print(brief.to_json())
