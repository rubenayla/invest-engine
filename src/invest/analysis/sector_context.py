from typing import Dict, Optional

from ..config.loader import load_sector_benchmarks
from ..config.schema import SectorBenchmarks


class SectorContext:
    """Provides sector-specific context for investment analysis."""

    def __init__(self, benchmarks_path: Optional[str] = None):
        """Initialize with sector benchmarks."""
        if benchmarks_path:
            self.benchmarks = load_sector_benchmarks(benchmarks_path)
        else:
            # Try to load default benchmarks
            try:
                from pathlib import Path

                default_path = (
                    Path(__file__).parent.parent.parent.parent
                    / "configs"
                    / "sector_benchmarks.yaml"
                )
                self.benchmarks = load_sector_benchmarks(default_path)
            except Exception:
                self.benchmarks = {}

    def get_sector_context(self, sector: str) -> Optional[SectorBenchmarks]:
        """Get benchmarks for a specific sector."""
        return self.benchmarks.get(sector)

    def adjust_expectations_for_sector(self, stock_data: Dict, sector: str) -> Dict:
        """Adjust valuation expectations based on sector characteristics."""
        sector_bench = self.get_sector_context(sector)
        if not sector_bench:
            return stock_data

        adjusted_data = stock_data.copy()

        # Adjust P/E expectations based on sector norms
        pe = stock_data.get("trailing_pe", 0)
        if pe and pe > 0:
            pe_min, pe_max = sector_bench.typical_pe_range

            # Flag if P/E is outside typical range
            if pe < pe_min * 0.7:
                adjusted_data["pe_flag"] = "unusually_low"
            elif pe > pe_max * 1.3:
                adjusted_data["pe_flag"] = "unusually_high"
            else:
                adjusted_data["pe_flag"] = "normal"

            # Calculate sector-adjusted P/E score
            sector_median_pe = (pe_min + pe_max) / 2
            adjusted_data["sector_adjusted_pe_score"] = max(
                0, (sector_median_pe - pe) / sector_median_pe * 100
            )

        # Adjust ROE expectations
        roe = stock_data.get("return_on_equity", 0)
        if roe and roe > 0:
            roe_min, roe_max = sector_bench.typical_roe_range

            if roe < roe_min * 0.8:
                adjusted_data["roe_flag"] = "below_sector_norm"
            elif roe > roe_max * 1.2:
                adjusted_data["roe_flag"] = "above_sector_norm"
            else:
                adjusted_data["roe_flag"] = "sector_typical"

            # Calculate sector-adjusted ROE score
            sector_median_roe = (roe_min + roe_max) / 2
            adjusted_data["sector_adjusted_roe_score"] = (roe / sector_median_roe) * 100

        # Add sector risk characteristics
        adjusted_data["sector_cyclicality"] = sector_bench.cyclicality
        adjusted_data["sector_capital_intensity"] = sector_bench.capital_intensity
        adjusted_data["sector_margin_stability"] = sector_bench.margin_stability

        return adjusted_data

    def get_sector_risk_adjustment(self, sector: str) -> float:
        """Get risk adjustment factor for sector (1.0 = neutral)."""
        sector_bench = self.get_sector_context(sector)
        if not sector_bench:
            return 1.0

        # Higher risk adjustment for more cyclical/volatile sectors
        risk_adjustments = {
            "high": 1.3,  # High cyclicality = higher risk
            "medium": 1.1,  # Medium cyclicality = slight risk increase
            "low": 0.9,  # Low cyclicality = risk decrease
        }

        return risk_adjustments.get(sector_bench.cyclicality, 1.0)

    def get_valuation_adjustment(self, sector: str) -> Dict[str, float]:
        """Get sector-specific valuation adjustments."""
        sector_bench = self.get_sector_context(sector)
        if not sector_bench:
            return {"pe_adjustment": 1.0, "growth_premium": 1.0, "risk_discount": 1.0}

        adjustments = {"pe_adjustment": 1.0, "growth_premium": 1.0, "risk_discount": 1.0}

        # Cyclical sectors get valuation discounts
        if sector_bench.cyclicality == "high":
            adjustments["pe_adjustment"] = 0.85  # Lower P/E multiples
            adjustments["risk_discount"] = 1.15  # Higher risk discount
        elif sector_bench.cyclicality == "low":
            adjustments["pe_adjustment"] = 1.1  # Premium for stability
            adjustments["risk_discount"] = 0.9  # Lower risk discount

        # Capital intensive sectors
        if sector_bench.capital_intensity == "high":
            adjustments["growth_premium"] = 0.9  # Lower growth premium due to reinvestment needs

        # Margin stability affects valuation predictability
        if sector_bench.margin_stability == "stable":
            adjustments["pe_adjustment"] *= 1.05  # Premium for predictability
        elif sector_bench.margin_stability == "volatile":
            adjustments["pe_adjustment"] *= 0.95  # Discount for unpredictability

        return adjustments

    def compare_to_sector_peers(self, stock_data: Dict, sector: str) -> Dict:
        """Compare stock metrics to sector benchmarks."""
        sector_bench = self.get_sector_context(sector)
        if not sector_bench:
            return {"sector_comparison": "no_benchmarks_available"}

        comparison = {
            "sector": sector,
            "vs_sector_pe": "unknown",
            "vs_sector_roe": "unknown",
            "vs_sector_roic": "unknown",
            "sector_characteristics": {
                "cyclicality": sector_bench.cyclicality,
                "capital_intensity": sector_bench.capital_intensity,
                "margin_stability": sector_bench.margin_stability,
            },
        }

        # P/E comparison
        pe = stock_data.get("trailing_pe", 0)
        if pe and pe > 0:
            pe_min, pe_max = sector_bench.typical_pe_range
            pe_mid = (pe_min + pe_max) / 2

            if pe < pe_min:
                comparison["vs_sector_pe"] = "below_range"
            elif pe > pe_max:
                comparison["vs_sector_pe"] = "above_range"
            elif pe < pe_mid:
                comparison["vs_sector_pe"] = "below_median"
            else:
                comparison["vs_sector_pe"] = "above_median"

        # ROE comparison
        roe = stock_data.get("return_on_equity", 0)
        if roe and roe > 0:
            roe_min, roe_max = sector_bench.typical_roe_range
            roe_mid = (roe_min + roe_max) / 2

            if roe < roe_min:
                comparison["vs_sector_roe"] = "below_range"
            elif roe > roe_max:
                comparison["vs_sector_roe"] = "above_range"
            elif roe < roe_mid:
                comparison["vs_sector_roe"] = "below_median"
            else:
                comparison["vs_sector_roe"] = "above_median"

        # ROIC comparison (if available/calculated)
        roic = stock_data.get("roic", 0)  # This would come from quality screening
        if roic and roic > 0:
            roic_min, roic_max = sector_bench.typical_roic_range
            roic_mid = (roic_min + roic_max) / 2

            if roic < roic_min:
                comparison["vs_sector_roic"] = "below_range"
            elif roic > roic_max:
                comparison["vs_sector_roic"] = "above_range"
            elif roic < roic_mid:
                comparison["vs_sector_roic"] = "below_median"
            else:
                comparison["vs_sector_roic"] = "above_median"

        return comparison

    def get_sector_specific_flags(self, stock_data: Dict, sector: str) -> list[str]:
        """Get sector-specific warning flags."""
        flags = []
        sector_bench = self.get_sector_context(sector)

        if not sector_bench:
            return flags

        # Cyclical sector flags
        if sector_bench.cyclicality == "high":
            flags.append("High cyclical risk - earnings may be at cycle peak/trough")

            # Check if margins look unusually high (potential cycle peak)
            roe = stock_data.get("return_on_equity", 0)
            if roe and roe > sector_bench.typical_roe_range[1] * 1.3:
                flags.append("ROE significantly above sector norm - possible cycle peak")

        # Capital intensity flags
        if sector_bench.capital_intensity == "high":
            debt_ratio = stock_data.get("debt_to_equity", 0)
            if debt_ratio and debt_ratio > 75:  # High debt in capital intensive sector
                flags.append("High debt in capital-intensive sector increases financial risk")

        # Margin stability flags
        if sector_bench.margin_stability == "volatile":
            flags.append("Sector has historically volatile margins - earnings predictability low")

        return flags
