import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

REQUIRED_COLUMNS = (
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
)

STATE_PATTERN = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class ValidatedFuelPriceRow:
    opis_truckstop_id: int
    truckstop_name: str
    address: str
    city: str
    state: str
    rack_id: int
    retail_price: Decimal
    source_row_hash: str


def _parse_positive_int(value: Any, field_name: str) -> tuple[int | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, f"{field_name} is required"

    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None, f"{field_name} must be a valid integer"

    if parsed <= 0:
        return None, f"{field_name} must be a positive integer"

    return parsed, None


def _parse_required_string(value: Any, field_name: str) -> tuple[str | None, str | None]:
    if value is None:
        return None, f"{field_name} is required"

    parsed = str(value).strip()
    if not parsed:
        return None, f"{field_name} is required"

    return parsed, None


def _parse_state(value: Any) -> tuple[str | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, "State is required"

    state = str(value).strip().upper()
    if not STATE_PATTERN.match(state):
        return None, "State must be a 2-letter code"

    return state, None


def _parse_retail_price(value: Any) -> tuple[Decimal | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, "Retail Price is required"

    try:
        price = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None, "Retail Price must be a valid decimal number"

    if price <= 0:
        return None, "Retail Price must be greater than zero"

    return price, None


def build_source_row_hash(
    opis_truckstop_id: int,
    truckstop_name: str,
    address: str,
    city: str,
    state: str,
    rack_id: int,
    retail_price: Decimal,
) -> str:
    payload = "|".join(
        [
            str(opis_truckstop_id),
            truckstop_name,
            address,
            city,
            state,
            str(rack_id),
            str(retail_price),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_fuel_price_row(row: dict[str, Any]) -> tuple[ValidatedFuelPriceRow | None, str | None]:
    opis_truckstop_id, error = _parse_positive_int(row.get("OPIS Truckstop ID"), "OPIS Truckstop ID")
    if error:
        return None, error

    truckstop_name, error = _parse_required_string(row.get("Truckstop Name"), "Truckstop Name")
    if error:
        return None, error

    address, error = _parse_required_string(row.get("Address"), "Address")
    if error:
        return None, error

    city, error = _parse_required_string(row.get("City"), "City")
    if error:
        return None, error

    state, error = _parse_state(row.get("State"))
    if error:
        return None, error

    rack_id, error = _parse_positive_int(row.get("Rack ID"), "Rack ID")
    if error:
        return None, error

    retail_price, error = _parse_retail_price(row.get("Retail Price"))
    if error:
        return None, error

    return (
        ValidatedFuelPriceRow(
            opis_truckstop_id=opis_truckstop_id,
            truckstop_name=truckstop_name,
            address=address,
            city=city,
            state=state,
            rack_id=rack_id,
            retail_price=retail_price,
            source_row_hash=build_source_row_hash(
                opis_truckstop_id,
                truckstop_name,
                address,
                city,
                state,
                rack_id,
                retail_price,
            ),
        ),
        None,
    )
