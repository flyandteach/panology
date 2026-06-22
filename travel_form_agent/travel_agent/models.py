from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json


def _parse_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Could not parse date: {value!r}")


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text or 0)


@dataclass
class Traveler:
    name: str
    name_last_first_initial: Optional[str] = None
    employee_id: Optional[str] = None
    class_title: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = "WA"
    zip_code: Optional[str] = None
    official_station: Optional[str] = None
    official_residence: Optional[str] = None
    regular_work_hours: Optional[str] = None
    supervisor_name: Optional[str] = None
    approving_authority_name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Traveler":
        return cls(**data)


@dataclass
class DailyExpenseLine:
    date: date
    trip_from: Optional[str] = None
    trip_to: Optional[str] = None
    depart: Optional[str] = None
    return_time: Optional[str] = None
    breakfast: float = 0.0
    lunch: float = 0.0
    dinner: float = 0.0
    lodging: float = 0.0
    miles: float = 0.0
    mileage_rate: float = 0.0
    pov_reason: Optional[str] = None
    other: float = 0.0
    purpose: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyExpenseLine":
        d = dict(data)
        d["date"] = _parse_date(d.get("date"))
        for k in ["breakfast", "lunch", "dinner", "lodging", "miles", "mileage_rate", "other"]:
            d[k] = money(d.get(k))
        return cls(**d)

    @property
    def mileage_total(self) -> float:
        return round(self.miles * self.mileage_rate, 2)

    @property
    def total(self) -> float:
        return round(
            self.breakfast + self.lunch + self.dinner + self.lodging + self.mileage_total + self.other,
            2,
        )


@dataclass
class AccountCode:
    work_order: Optional[str] = None
    group: Optional[str] = None
    work_op: Optional[str] = None
    object_code: Optional[str] = None
    org_code: Optional[str] = None
    amount: float = 0.0
    cont_sec: Optional[str] = None
    bal_sheet: Optional[str] = None
    non_participating: Optional[str] = None

    # Newer travel request charge-code fields, when applicable.
    cited_authority: Optional[str] = None
    fund: Optional[str] = None
    appropriation: Optional[str] = None
    unit: Optional[str] = None
    subunit: Optional[str] = None
    activity: Optional[str] = None
    function: Optional[str] = None
    program: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountCode":
        d = dict(data)
        d["amount"] = money(d.get("amount"))
        return cls(**d)


@dataclass
class OtherExpense:
    date: Optional[date] = None
    paid_to: Optional[str] = None
    for_what: Optional[str] = None
    amount: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OtherExpense":
        d = dict(data)
        d["date"] = _parse_date(d.get("date"))
        d["amount"] = money(d.get("amount"))
        return cls(**d)


@dataclass
class TravelIntake:
    traveler: Traveler
    event_title: str
    destination_city: str
    departure_datetime: str
    return_datetime: str
    meeting_begin_datetime: str
    meeting_end_datetime: str
    payment_methods: List[str] = field(default_factory=list)
    other_payment_method_description: Optional[str] = None
    registration_fee: float = 0.0
    airfare: float = 0.0
    subsistence_days: Optional[float] = None
    subsistence_rate: Optional[float] = None
    lodging_days: Optional[float] = None
    lodging_rate: Optional[float] = None
    hotel_name: Optional[str] = None
    hotel_city: Optional[str] = None
    comments: Optional[str] = None
    daily_expenses: List[DailyExpenseLine] = field(default_factory=list)
    account_codes: List[AccountCode] = field(default_factory=list)
    other_expenses: List[OtherExpense] = field(default_factory=list)
    request_other_fees: float = 0.0
    remarks: Optional[str] = None
    travel_advance: float = 0.0
    signature_date: Optional[date] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TravelIntake":
        traveler = Traveler.from_dict(data.get("traveler", {}))
        daily = [DailyExpenseLine.from_dict(x) for x in data.get("daily_expenses", [])]
        accounts = [AccountCode.from_dict(x) for x in data.get("account_codes", [])]
        others = [OtherExpense.from_dict(x) for x in data.get("other_expenses", [])]
        d = dict(data)
        d["traveler"] = traveler
        d["daily_expenses"] = daily
        d["account_codes"] = accounts
        d["other_expenses"] = others
        d["registration_fee"] = money(d.get("registration_fee"))
        d["airfare"] = money(d.get("airfare"))
        d["travel_advance"] = money(d.get("travel_advance"))
        d["request_other_fees"] = money(d.get("request_other_fees"))
        d["signature_date"] = _parse_date(d.get("signature_date"))
        for k in ["subsistence_days", "subsistence_rate", "lodging_days", "lodging_rate"]:
            d[k] = None if d.get(k) in (None, "") else money(d.get(k))
        return cls(**d)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "TravelIntake":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def validate(self) -> List[str]:
        missing: List[str] = []
        required = {
            "traveler.name": self.traveler.name,
            "event_title": self.event_title,
            "destination_city": self.destination_city,
            "departure_datetime": self.departure_datetime,
            "return_datetime": self.return_datetime,
            "meeting_begin_datetime": self.meeting_begin_datetime,
            "meeting_end_datetime": self.meeting_end_datetime,
        }
        for field_name, value in required.items():
            if value in (None, ""):
                missing.append(field_name)
        if not self.daily_expenses:
            missing.append("daily_expenses")
        return missing

    @property
    def subsistence_total(self) -> float:
        if self.subsistence_days is not None and self.subsistence_rate is not None:
            return round(self.subsistence_days * self.subsistence_rate, 2)
        return round(sum(x.breakfast + x.lunch + x.dinner for x in self.daily_expenses), 2)

    @property
    def lodging_total(self) -> float:
        if self.lodging_days is not None and self.lodging_rate is not None:
            return round(self.lodging_days * self.lodging_rate, 2)
        return round(sum(x.lodging for x in self.daily_expenses), 2)

    @property
    def mileage_total(self) -> float:
        return round(sum(x.mileage_total for x in self.daily_expenses), 2)

    @property
    def daily_other_total(self) -> float:
        return round(sum(x.other for x in self.daily_expenses), 2)

    @property
    def other_expenses_total(self) -> float:
        return round(sum(x.amount for x in self.other_expenses), 2)

    @property
    def other_fees_total_for_request(self) -> float:
        # Request form category excludes registration and airfare, but includes mileage and any additional request-only fees.
        # Receipt-level items such as registration can still be listed in `other_expenses` for the 133-103 detail section
        # without being double-counted here.
        return round(self.mileage_total + self.daily_other_total + self.request_other_fees, 2)

    @property
    def estimated_total(self) -> float:
        return round(
            self.registration_fee
            + self.airfare
            + self.subsistence_total
            + self.lodging_total
            + self.other_fees_total_for_request,
            2,
        )

    @property
    def expense_voucher_total(self) -> float:
        return round(sum(x.total for x in self.daily_expenses) + self.other_expenses_total, 2)
