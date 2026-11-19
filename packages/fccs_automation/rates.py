"""Oracle FCCS Exchange Rates Manager and Currency Translation Engine."""
import csv
import io
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from typing import Literal

from packages.reconciliation.contracts import money


@dataclass
class FXRate:
    from_currency: str
    to_currency: str
    rate: str
    rate_type: str = "Closing"
    scenario: str = "Actual"
    year: str = "FY26"
    period: str = "Nov"

    def __post_init__(self):
        self.from_currency = self.from_currency.upper().strip()
        self.to_currency = self.to_currency.upper().strip()
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", self.rate):
            raise ValueError(f"Invalid decimal rate: {self.rate}")


class RatesManager:
    """Manages exchange rates and performs deterministic currency translations for FCCS."""

    def __init__(self, initial_rates: list[FXRate] | None = None):
        self.rates: dict[tuple[str, str, str, str, str, str], FXRate] = {}
        if initial_rates:
            for rate in initial_rates:
                self.add_rate(rate)

    def add_rate(self, rate: FXRate):
        key = (
            rate.from_currency,
            rate.to_currency,
            rate.rate_type,
            rate.scenario,
            rate.year,
            rate.period,
        )
        self.rates[key] = rate

    def load_from_list(self, rate_dicts: list[dict]):
        for item in rate_dicts:
            self.add_rate(
                FXRate(
                    from_currency=item["from_currency"],
                    to_currency=item["to_currency"],
                    rate=str(item["rate"]),
                    rate_type=item.get("rate_type", "Closing"),
                    scenario=item.get("scenario", "Actual"),
                    year=item.get("year", "FY26"),
                    period=item.get("period", "Nov"),
                )
            )

    def load_from_csv(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            self.add_rate(
                FXRate(
                    from_currency=row["from_currency"],
                    to_currency=row["to_currency"],
                    rate=row["rate"],
                    rate_type=row.get("rate_type", "Closing"),
                    scenario=row.get("scenario", "Actual"),
                    year=row.get("year", "FY26"),
                    period=row.get("period", "Nov"),
                )
            )

    def get_rate(
        self,
        from_curr: str,
        to_curr: str,
        period: str = "Nov",
        year: str = "FY26",
        scenario: str = "Actual",
        rate_type: str = "Closing",
    ) -> Decimal:
        from_curr, to_curr = from_curr.upper().strip(), to_curr.upper().strip()
        if from_curr == to_curr:
            return Decimal("1.0")

        key = (from_curr, to_curr, rate_type, scenario, year, period)
        if key in self.rates:
            return money(self.rates[key].rate)

        # Check reciprocal rate
        inverse_key = (to_curr, from_curr, rate_type, scenario, year, period)
        if inverse_key in self.rates:
            with localcontext() as ctx:
                ctx.prec = 100
                return Decimal("1.0") / money(self.rates[inverse_key].rate)

        raise ValueError(
            f"Missing required FX rate for {from_curr}->{to_curr} ({rate_type}, {scenario}, {year}, {period})"
        )

    def translate(
        self,
        amount: str | Decimal,
        from_curr: str,
        to_curr: str,
        period: str = "Nov",
        year: str = "FY26",
        scenario: str = "Actual",
        rate_type: str = "Closing",
        minor_units: int = 2,
        rounding: Literal["HALF_EVEN", "HALF_UP"] = "HALF_EVEN",
    ) -> tuple[Decimal, Decimal]:
        """Translates amount using local 100-digit precision.

        Returns (unrounded_amount, rounded_amount).
        """
        val = money(str(amount)) if isinstance(amount, (str, int, float)) else amount
        rate = self.get_rate(from_curr, to_curr, period, year, scenario, rate_type)

        with localcontext() as ctx:
            ctx.prec = 100
            unrounded = val * rate
            scale = Decimal("10") ** -minor_units
            round_mode = ROUND_HALF_EVEN if rounding == "HALF_EVEN" else ROUND_HALF_UP
            rounded = unrounded.quantize(scale, rounding=round_mode)
            return unrounded, rounded

    def export_fccs_rates_csv(self) -> str:
        """Generates standard Oracle FCCS Currency Rates Integration CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["From_Currency", "To_Currency", "Rate_Type", "Scenario", "Year", "Period", "Rate"]
        )
        for r in self.rates.values():
            writer.writerow(
                [
                    r.from_currency,
                    r.to_currency,
                    r.rate_type,
                    r.scenario,
                    r.year,
                    r.period,
                    r.rate,
                ]
            )
        return output.getvalue()

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self.rates.values()]
