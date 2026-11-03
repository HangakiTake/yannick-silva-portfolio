"""Reference allocator for a ratio utility billing (RUBS) workbook.

Money is integer cents. Percentages are entered as points (10 means 10%)
and converted to basis points so half-up rounding does not depend on binary
floats. The Excel workbook implements the same integer rules.

Allocation order for a valid bill
---------------------------------
1. Convert the bill to cents (half-up).
2. Take the owner-paid percent off the top.
3. Split the remaining pool across tenant weights and owner (vacancy) weights
   with the largest-remainder method. Tie: lower bucket key wins. The key is
   ``unit_id|T`` or ``unit_id|O``.
4. Take any unit discount from that unit's tenant gross and add it to Owner.
5. If the pool has no positive weight, charge the pool to Owner and flag it.

A unit marked vacant contributes no tenant weight. Occupancy dates on that
unit are ignored for the math and reported as an exception. Partial-month
occupancy is an inclusive day count inside the service period.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

METHODS = ("occupant_days", "per_unit", "square_footage")
PARTIALS = ("absorb", "owner")
OPEN_ENDED = date(2099, 12, 31)


@dataclass(frozen=True)
class Property:
    property_id: str
    name: str
    address: str
    city: str
    notes: str = ""


@dataclass(frozen=True)
class Unit:
    unit_id: str
    property_id: str
    is_vacant: bool
    discount_points: Decimal
    sqft: int | None
    exclude_utilities: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Occupancy:
    occupancy_id: str
    unit_id: str
    occupants: int
    move_in: date | None
    move_out: date | None = None
    notes: str = ""


@dataclass(frozen=True)
class Bill:
    bill_id: str
    property_id: str
    utility: str
    amount: Decimal
    period_start: date | None
    period_end: date | None
    notes: str = ""


@dataclass(frozen=True)
class Rule:
    property_id: str
    utility: str
    method: str
    owner_paid_points: Decimal
    partial_vacancy: str
    vacant_equivalent: int
    notes: str = ""


@dataclass(frozen=True)
class Dataset:
    properties: tuple[Property, ...] | list[Property]
    units: tuple[Unit, ...] | list[Unit]
    occupancy: tuple[Occupancy, ...] | list[Occupancy]
    bills: tuple[Bill, ...] | list[Bill]
    rules: tuple[Rule, ...] | list[Rule]


@dataclass(frozen=True)
class Line:
    unit_id: str
    occupant_days: int
    occupied_days: int
    tenant_weight: int
    owner_weight: int
    tenant_gross_cents: int
    owner_gross_cents: int
    discount_cents: int
    tenant_net_cents: int
    excluded: bool


@dataclass(frozen=True)
class BillResult:
    bill_id: str
    property_id: str
    utility: str
    included: bool
    amount_cents: int
    owner_pct_cents: int
    pool_cents: int
    unallocated_pool_cents: int
    no_eligible_weight: bool
    lines: tuple[Line, ...]

    @property
    def tenant_cents(self) -> int:
        return sum(line.tenant_net_cents for line in self.lines)

    @property
    def owner_cents(self) -> int:
        variable = sum(line.owner_gross_cents + line.discount_cents for line in self.lines)
        return self.owner_pct_cents + self.unallocated_pool_cents + variable


@dataclass(frozen=True)
class Allocation:
    bills: tuple[BillResult, ...]


@dataclass(frozen=True)
class ExceptionItem:
    code: str
    message: str
    property_id: str | None = None
    unit_id: str | None = None
    utility: str | None = None
    bill_id: str | None = None


def money_to_cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def points_to_bps(points: Decimal) -> int:
    """10 points (meaning 10%) -> 1000 basis points."""
    return int((Decimal(points) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percent_of_cents(cents: int, bps: int) -> int:
    """Half-up percentage of an integer cent amount. ``bps`` is out of 10_000."""
    if cents <= 0 or bps <= 0:
        return 0
    return (cents * bps + 5_000) // 10_000


def overlap_days(move_in: date | None, move_out: date | None, start: date, end: date) -> int:
    if move_in is None or start is None or end is None or end < start:
        return 0
    last = end if move_out is None else move_out
    first = move_in if move_in > start else start
    last = last if last < end else end
    if last < first:
        return 0
    return (last - first).days + 1


def _period_days(start: date, end: date) -> int:
    return (end - start).days + 1


def _valid_period(bill: Bill) -> bool:
    if bill.period_start is None or bill.period_end is None:
        return False
    if bill.period_end < bill.period_start:
        return False
    return _period_days(bill.period_start, bill.period_end) <= 366


def _structurally_valid(bill: Bill) -> bool:
    return bill.amount is not None and bill.amount >= 0 and _valid_period(bill)


def _utility_key(value: str) -> str:
    return value.strip().lower()


def _excluded(unit: Unit, utility: str) -> bool:
    key = _utility_key(utility)
    return any(_utility_key(name) == key for name in unit.exclude_utilities)


def _rule_for(rules: list[Rule], property_id: str, utility: str) -> Rule | None:
    key = _utility_key(utility)
    matches = [rule for rule in rules if rule.property_id == property_id and _utility_key(rule.utility) == key]
    return matches[0] if matches else None


def _usable_rule(rule: Rule | None) -> bool:
    if rule is None:
        return False
    if rule.method not in METHODS or rule.partial_vacancy not in PARTIALS:
        return False
    if rule.owner_paid_points < 0 or rule.owner_paid_points > 100:
        return False
    if rule.vacant_equivalent < 0:
        return False
    return True


def _active_records(occupancy: list[Occupancy], unit: Unit) -> list[Occupancy]:
    if unit.is_vacant:
        return []
    return [
        record
        for record in occupancy
        if record.unit_id == unit.unit_id and record.occupants > 0 and record.move_in is not None
    ]


def _occupant_days(records: list[Occupancy], start: date, end: date) -> int:
    return sum(record.occupants * overlap_days(record.move_in, record.move_out, start, end) for record in records)


def _occupied_days(records: list[Occupancy], start: date, end: date) -> int:
    """Sum of each stint's days inside the period, capped at the period length.

    Non-overlapping stints equal the union of occupied days. Overlapping
    stints are an input error (flagged separately) and can overstate the day
    count up to the cap.
    """
    raw = sum(overlap_days(record.move_in, record.move_out, start, end) for record in records)
    return min(_period_days(start, end), raw)


def _allocate_cents(total: int, buckets: list[tuple[str, int]]) -> dict[str, int]:
    shares = {key: 0 for key, _weight in buckets}
    positive = [(key, weight) for key, weight in buckets if weight > 0]
    if total <= 0 or not positive:
        return shares
    denominator = sum(weight for _key, weight in positive)
    floors: dict[str, int] = {}
    remainders: dict[str, int] = {}
    for key, weight in positive:
        product = total * weight
        floors[key] = product // denominator
        remainders[key] = product % denominator
    leftover = total - sum(floors.values())
    order = sorted(positive, key=lambda item: (-remainders[item[0]], item[0]))
    for index in range(leftover):
        floors[order[index][0]] += 1
    shares.update(floors)
    return shares


def _empty_result(bill: Bill, included: bool, amount_cents: int, lines: tuple[Line, ...] = ()) -> BillResult:
    return BillResult(
        bill_id=bill.bill_id,
        property_id=bill.property_id,
        utility=bill.utility,
        included=included,
        amount_cents=amount_cents,
        owner_pct_cents=0,
        pool_cents=0,
        unallocated_pool_cents=0,
        no_eligible_weight=False,
        lines=lines,
    )


def allocate_bill(bill: Bill, data: Dataset) -> BillResult:
    amount_cents = 0 if bill.amount is None else money_to_cents(bill.amount)
    units = [unit for unit in data.units if unit.property_id == bill.property_id]
    if not _structurally_valid(bill):
        return _empty_result(bill, included=False, amount_cents=amount_cents)

    rule = _rule_for(list(data.rules), bill.property_id, bill.utility)
    zero_lines = tuple(_zero_line(unit) for unit in units)
    if rule is None:
        return BillResult(
            bill_id=bill.bill_id,
            property_id=bill.property_id,
            utility=bill.utility,
            included=True,
            amount_cents=amount_cents,
            owner_pct_cents=0,
            pool_cents=0,
            unallocated_pool_cents=amount_cents,
            no_eligible_weight=False,
            lines=zero_lines,
        )
    if not _usable_rule(rule):
        return _empty_result(bill, included=False, amount_cents=amount_cents, lines=zero_lines)

    assert bill.period_start is not None and bill.period_end is not None
    start, end = bill.period_start, bill.period_end
    owner_bps = points_to_bps(rule.owner_paid_points)
    owner_pct_cents = percent_of_cents(amount_cents, owner_bps)
    pool = amount_cents - owner_pct_cents

    prepared: list[tuple[Unit, int, int, int, int, bool]] = []
    buckets: list[tuple[str, int]] = []
    for unit in units:
        excluded = _excluded(unit, bill.utility)
        records = _active_records(list(data.occupancy), unit)
        occupant_days = _occupant_days(records, start, end)
        occupied_days = _occupied_days(records, start, end)
        tenant_weight, owner_weight = _weights(unit, rule, occupant_days, occupied_days, _period_days(start, end), excluded)
        prepared.append((unit, occupant_days, occupied_days, tenant_weight, owner_weight, excluded))
        buckets.append((f"{unit.unit_id}|T", tenant_weight))
        buckets.append((f"{unit.unit_id}|O", owner_weight))

    no_weight = pool > 0 and sum(weight for _key, weight in buckets) == 0
    shares = {} if no_weight else _allocate_cents(pool, buckets)
    lines: list[Line] = []
    for unit, occupant_days, occupied_days, tenant_weight, owner_weight, excluded in prepared:
        gross_tenant = 0 if no_weight else shares.get(f"{unit.unit_id}|T", 0)
        gross_owner = 0 if no_weight else shares.get(f"{unit.unit_id}|O", 0)
        discount_bps = points_to_bps(unit.discount_points) if 0 <= unit.discount_points <= 100 else 0
        discount = percent_of_cents(gross_tenant, discount_bps)
        lines.append(
            Line(
                unit_id=unit.unit_id,
                occupant_days=occupant_days,
                occupied_days=occupied_days,
                tenant_weight=tenant_weight,
                owner_weight=owner_weight,
                tenant_gross_cents=gross_tenant,
                owner_gross_cents=gross_owner,
                discount_cents=discount,
                tenant_net_cents=gross_tenant - discount,
                excluded=excluded,
            )
        )
    return BillResult(
        bill_id=bill.bill_id,
        property_id=bill.property_id,
        utility=bill.utility,
        included=True,
        amount_cents=amount_cents,
        owner_pct_cents=owner_pct_cents,
        pool_cents=pool,
        unallocated_pool_cents=pool if no_weight else 0,
        no_eligible_weight=no_weight,
        lines=tuple(lines),
    )


def _zero_line(unit: Unit) -> Line:
    return Line(
        unit_id=unit.unit_id,
        occupant_days=0,
        occupied_days=0,
        tenant_weight=0,
        owner_weight=0,
        tenant_gross_cents=0,
        owner_gross_cents=0,
        discount_cents=0,
        tenant_net_cents=0,
        excluded=False,
    )


def _weights(
    unit: Unit,
    rule: Rule,
    occupant_days: int,
    occupied_days: int,
    period_days: int,
    excluded: bool,
) -> tuple[int, int]:
    if excluded:
        return (0, 0)
    vacant_days = period_days - occupied_days
    charge_owner = rule.partial_vacancy == "owner"
    if rule.method == "occupant_days":
        tenant = 0 if unit.is_vacant else occupant_days
        owner = rule.vacant_equivalent * vacant_days if charge_owner else 0
        return (tenant, owner)
    if rule.method == "per_unit":
        return (occupied_days, vacant_days if charge_owner else 0)
    sqft = unit.sqft or 0
    if sqft <= 0:
        return (0, 0)
    return (sqft * occupied_days, sqft * vacant_days if charge_owner else 0)


def allocate_dataset(data: Dataset) -> Allocation:
    return Allocation(tuple(allocate_bill(bill, data) for bill in data.bills))


def explain_unit(data: Dataset, bill_id: str, unit_id: str) -> Line:
    result = allocate_dataset(data)
    bill = next((item for item in result.bills if item.bill_id == bill_id), None)
    if bill is None or not bill.included:
        raise KeyError(f"{bill_id} is not an allocated bill")
    line = next((item for item in bill.lines if item.unit_id == unit_id), None)
    if line is None:
        raise KeyError(f"{unit_id} is not on {bill_id}")
    return line


def collect_exceptions(data: Dataset) -> tuple[ExceptionItem, ...]:
    issues: list[ExceptionItem] = []
    properties = {prop.property_id for prop in data.properties}
    unit_ids = [unit.unit_id for unit in data.units]
    seen_units: set[str] = set()
    for unit in data.units:
        if unit.unit_id in seen_units:
            issues.append(ExceptionItem("duplicate_unit", f"Duplicate unit id {unit.unit_id}.", unit.property_id, unit.unit_id))
        seen_units.add(unit.unit_id)
        if unit.property_id not in properties:
            issues.append(
                ExceptionItem(
                    "unknown_property",
                    f"Unit {unit.unit_id} references unknown property {unit.property_id}.",
                    unit.property_id,
                    unit.unit_id,
                )
            )
        if unit.discount_points < 0 or unit.discount_points > 100:
            issues.append(
                ExceptionItem(
                    "bad_discount",
                    f"Discount for {unit.unit_id} must be between 0 and 100 (enter 10 for 10%).",
                    unit.property_id,
                    unit.unit_id,
                )
            )
        property_uses_sqft = any(
            rule.property_id == unit.property_id and rule.method == "square_footage" for rule in data.rules
        )
        if property_uses_sqft and (unit.sqft is None or unit.sqft <= 0):
            issues.append(
                ExceptionItem(
                    "missing_sqft",
                    f"{unit.unit_id} needs square footage because a rule allocates by square footage.",
                    unit.property_id,
                    unit.unit_id,
                )
            )
        if unit.is_vacant and any(record.unit_id == unit.unit_id and record.occupants > 0 for record in data.occupancy):
            issues.append(
                ExceptionItem(
                    "vacant_has_occupancy",
                    f"Occupancy is recorded on {unit.unit_id}, which is marked vacant. The vacant flag wins and the unit is not billed as occupied.",
                    unit.property_id,
                    unit.unit_id,
                )
            )

    known_units = set(unit_ids)
    by_unit: dict[str, list[Occupancy]] = {}
    for record in data.occupancy:
        by_unit.setdefault(record.unit_id, []).append(record)
        if record.unit_id not in known_units:
            issues.append(
                ExceptionItem(
                    "unknown_unit",
                    f"Occupancy {record.occupancy_id} references unknown unit {record.unit_id}.",
                    unit_id=record.unit_id,
                )
            )
        if record.occupants < 0 or record.move_in is None or (
            record.move_out is not None and record.move_in is not None and record.move_out < record.move_in
        ):
            issues.append(
                ExceptionItem(
                    "bad_occupancy",
                    f"Occupancy {record.occupancy_id} has a negative count or an invalid date range.",
                    unit_id=record.unit_id,
                )
            )
    for unit_id, records in by_unit.items():
        ordered = [record for record in records if record.move_in is not None and record.occupants > 0]
        for index, left in enumerate(ordered):
            left_end = left.move_out or OPEN_ENDED
            for right in ordered[index + 1 :]:
                right_end = right.move_out or OPEN_ENDED
                assert right.move_in is not None
                if left.move_in <= right_end and right.move_in <= left_end:
                    issues.append(
                        ExceptionItem(
                            "occupancy_overlap",
                            f"Occupancy {left.occupancy_id} overlaps {right.occupancy_id} on {unit_id}. Per-unit and square-footage day counts can overstate occupied days until this is corrected.",
                            unit_id=unit_id,
                        )
                    )

    seen_rules: set[tuple[str, str]] = set()
    for rule in data.rules:
        rule_key = (rule.property_id, _utility_key(rule.utility))
        if rule_key in seen_rules:
            issues.append(
                ExceptionItem(
                    "duplicate_rule",
                    f"Duplicate rule for {rule.property_id} {rule.utility}. The first rule is the one that allocates.",
                    rule.property_id,
                    utility=rule.utility,
                )
            )
        seen_rules.add(rule_key)

    seen_bills: set[str] = set()
    for bill in data.bills:
        if bill.bill_id in seen_bills:
            issues.append(
                ExceptionItem("duplicate_bill_id", f"Duplicate bill id {bill.bill_id}.", bill.property_id, utility=bill.utility, bill_id=bill.bill_id)
            )
        seen_bills.add(bill.bill_id)
        if bill.property_id not in properties:
            issues.append(
                ExceptionItem(
                    "unknown_property",
                    f"Bill {bill.bill_id} references unknown property {bill.property_id}.",
                    bill.property_id,
                    utility=bill.utility,
                    bill_id=bill.bill_id,
                )
            )
        if bill.amount is None:
            issues.append(ExceptionItem("blank_amount", f"Bill {bill.bill_id} has a blank amount.", bill.property_id, utility=bill.utility, bill_id=bill.bill_id))
        elif bill.amount < 0:
            issues.append(
                ExceptionItem(
                    "negative_bill",
                    f"Negative bill amount on {bill.bill_id}; this row was not allocated.",
                    bill.property_id,
                    utility=bill.utility,
                    bill_id=bill.bill_id,
                )
            )
        if bill.period_start is None or bill.period_end is None or (
            bill.period_start is not None and bill.period_end is not None and bill.period_end < bill.period_start
        ):
            issues.append(
                ExceptionItem(
                    "invalid_period",
                    f"Bill {bill.bill_id} has a blank or backwards service period.",
                    bill.property_id,
                    utility=bill.utility,
                    bill_id=bill.bill_id,
                )
            )
        elif bill.period_start is not None and bill.period_end is not None and _period_days(bill.period_start, bill.period_end) > 366:
            issues.append(
                ExceptionItem(
                    "period_too_long",
                    f"Bill {bill.bill_id} covers more than 366 days.",
                    bill.property_id,
                    utility=bill.utility,
                    bill_id=bill.bill_id,
                )
            )

    for rule in data.rules:
        if rule.owner_paid_points < 0 or rule.owner_paid_points > 100:
            issues.append(
                ExceptionItem(
                    "bad_owner_pct",
                    f"Owner-paid percent for {rule.property_id} {rule.utility} must be between 0 and 100 (enter 15 for 15%).",
                    rule.property_id,
                    utility=rule.utility,
                )
            )
        if rule.method not in METHODS:
            issues.append(
                ExceptionItem(
                    "bad_method",
                    f"Unknown method {rule.method!r} for {rule.property_id} {rule.utility}.",
                    rule.property_id,
                    utility=rule.utility,
                )
            )
        if rule.partial_vacancy not in PARTIALS:
            issues.append(
                ExceptionItem(
                    "bad_partial",
                    f"Partial vacancy for {rule.property_id} {rule.utility} must be absorb or owner.",
                    rule.property_id,
                    utility=rule.utility,
                )
            )
        if rule.vacant_equivalent < 0:
            issues.append(
                ExceptionItem(
                    "bad_vacant_equivalent",
                    f"Vacant equivalent for {rule.property_id} {rule.utility} cannot be negative. The bill was not allocated.",
                    rule.property_id,
                    utility=rule.utility,
                )
            )

    valid = [bill for bill in data.bills if _structurally_valid(bill)]
    for bill in valid:
        if _rule_for(list(data.rules), bill.property_id, bill.utility) is None:
            issues.append(
                ExceptionItem(
                    "missing_rule",
                    f"No allocation rule for {bill.property_id} {bill.utility}. The bill was charged to Owner.",
                    bill.property_id,
                    utility=bill.utility,
                    bill_id=bill.bill_id,
                )
            )
        assert bill.period_start is not None and bill.period_end is not None
        earlier = [
            other.period_end
            for other in valid
            if other.bill_id != bill.bill_id
            and other.property_id == bill.property_id
            and _utility_key(other.utility) == _utility_key(bill.utility)
            and other.period_end is not None
            and other.period_end < bill.period_start
        ]
        if earlier:
            previous = max(end for end in earlier if end is not None)
            if bill.period_start > previous + timedelta(days=1):
                gap_start = previous + timedelta(days=1)
                gap_end = bill.period_start - timedelta(days=1)
                issues.append(
                    ExceptionItem(
                        "period_gap",
                        f"Service period gap from {gap_start.isoformat()} through {gap_end.isoformat()} before {bill.bill_id}.",
                        bill.property_id,
                        utility=bill.utility,
                        bill_id=bill.bill_id,
                    )
                )
        for other in valid:
            if other.bill_id == bill.bill_id or other.property_id != bill.property_id:
                continue
            if _utility_key(other.utility) != _utility_key(bill.utility):
                continue
            assert other.period_start is not None and other.period_end is not None
            if other.period_start <= bill.period_end and other.period_end >= bill.period_start:
                issues.append(
                    ExceptionItem(
                        "period_overlap",
                        f"{bill.bill_id} overlaps {other.bill_id}. Both bills are still allocated; shorten or remove one.",
                        bill.property_id,
                        utility=bill.utility,
                        bill_id=bill.bill_id,
                    )
                )

    for bill_result in allocate_dataset(data).bills:
        if bill_result.no_eligible_weight:
            issues.append(
                ExceptionItem(
                    "no_eligible_weight",
                    f"No eligible weight on {bill_result.bill_id}; the tenant pool was assigned to Owner.",
                    bill_result.property_id,
                    utility=bill_result.utility,
                    bill_id=bill_result.bill_id,
                )
            )
    return tuple(issues)


def demo_dataset() -> Dataset:
    """Synthetic portfolio: three properties, one messy March, plus a short February water bill."""
    properties = [
        Property("HC", "Harbor Court", "100 Harbor Lane", "Port Elm", "Synthetic. Not a real community."),
        Property("MT", "Maple Terrace", "240 Maple Avenue", "Millhaven", "Synthetic. Not a real community."),
        Property("CS", "Cedar Station", "15 Cedar Station Road", "Oak Crossing", "Synthetic. Not a real community."),
    ]
    units = [
        Unit("HC-01", "HC", False, Decimal("0"), None, (), "Two residents all month."),
        Unit("HC-02", "HC", False, Decimal("0"), None, (), "Move-in on 16 March."),
        Unit("HC-03", "HC", True, Decimal("0"), None, (), "Vacant. A conflicting occupancy row is seeded on purpose."),
        Unit("HC-04", "HC", False, Decimal("10"), None, ("gas",), "10% concession. No gas hookup."),
        Unit("MT-01", "MT", False, Decimal("0"), 650, ()),
        Unit("MT-02", "MT", False, Decimal("0"), 720, (), "One household out on 12 March, the next in on 20 March."),
        Unit("MT-03", "MT", False, Decimal("0"), 980, ()),
        Unit("MT-04", "MT", False, Decimal("0"), 800, ()),
        Unit("MT-05", "MT", True, Decimal("0"), 540, (), "Vacant all month."),
        Unit("MT-06", "MT", False, Decimal("0"), 610, ()),
        Unit("MT-07", "MT", False, Decimal("0"), 1100, ()),
        Unit("MT-08", "MT", False, Decimal("0"), 870, ()),
        Unit("CS-01", "CS", False, Decimal("0"), None, ()),
        Unit("CS-02", "CS", False, Decimal("0"), None, ()),
        Unit("CS-03", "CS", False, Decimal("0"), None, (), "Move-in on 10 March."),
        Unit("CS-04", "CS", False, Decimal("0"), None, ()),
        Unit("CS-05", "CS", False, Decimal("0"), None, ()),
        Unit("CS-06", "CS", False, Decimal("0"), None, ()),
        Unit("CS-07", "CS", True, Decimal("0"), None, (), "Vacant all month."),
        Unit("CS-08", "CS", False, Decimal("0"), None, ()),
        Unit("CS-09", "CS", False, Decimal("0"), None, ()),
        Unit("CS-10", "CS", False, Decimal("0"), None, ()),
        Unit("CS-11", "CS", False, Decimal("0"), None, ()),
        Unit("CS-12", "CS", False, Decimal("0"), None, ("gas",), "No gas hookup."),
    ]
    occupancy = [
        Occupancy("HC-01-RES", "HC-01", 2, date(2025, 1, 1), None, "In residence before the sample bills."),
        Occupancy("HC-02-RES", "HC-02", 1, date(2026, 3, 16), None, "Mid-month move-in."),
        Occupancy("HC-03-BAD", "HC-03", 1, date(2026, 3, 1), date(2026, 3, 31), "Seeded error: occupancy on a vacant unit."),
        Occupancy("HC-04-RES", "HC-04", 3, date(2025, 1, 1)),
        Occupancy("MT-01-RES", "MT-01", 1, date(2025, 1, 1)),
        Occupancy("MT-02-A", "MT-02", 2, date(2025, 1, 1), date(2026, 3, 12), "Moved out 12 March."),
        Occupancy("MT-02-B", "MT-02", 1, date(2026, 3, 20), None, "Moved in 20 March."),
        Occupancy("MT-03-RES", "MT-03", 4, date(2025, 6, 1)),
        Occupancy("MT-04-RES", "MT-04", 2, date(2025, 1, 1)),
        Occupancy("MT-06-RES", "MT-06", 1, date(2025, 2, 1)),
        Occupancy("MT-07-RES", "MT-07", 3, date(2025, 1, 1)),
        Occupancy("MT-08-RES", "MT-08", 2, date(2024, 11, 15)),
        Occupancy("CS-01-RES", "CS-01", 2, date(2024, 8, 1)),
        Occupancy("CS-02-RES", "CS-02", 1, date(2025, 1, 1)),
        Occupancy("CS-03-RES", "CS-03", 2, date(2026, 3, 10), None, "Mid-month move-in."),
        Occupancy("CS-04-RES", "CS-04", 3, date(2025, 3, 1)),
        Occupancy("CS-05-RES", "CS-05", 2, date(2025, 1, 1)),
        Occupancy("CS-06-RES", "CS-06", 4, date(2024, 12, 1)),
        Occupancy("CS-08-RES", "CS-08", 1, date(2025, 5, 1)),
        Occupancy("CS-09-RES", "CS-09", 2, date(2025, 1, 15)),
        Occupancy("CS-10-RES", "CS-10", 5, date(2025, 2, 1)),
        Occupancy("CS-11-RES", "CS-11", 2, date(2025, 7, 1)),
        Occupancy("CS-12-RES", "CS-12", 1, date(2025, 1, 1)),
    ]
    march = (date(2026, 3, 1), date(2026, 3, 31))
    bills = [
        Bill("HC-W-2026-02", "HC", "water", Decimal("188.41"), date(2026, 2, 1), date(2026, 2, 26), "Seeded gap: period ends 26 Feb, so 27-28 Feb are uncovered."),
        Bill("HC-W-2026-03", "HC", "water", Decimal("412.37"), *march, "Occupant-days. Vacancy is absorbed by occupied units."),
        Bill("HC-S-2026-03", "HC", "sewer", Decimal("198.05"), *march),
        Bill("HC-T-2026-03", "HC", "trash", Decimal("160.00"), *march, "15% owner-paid, then per-unit with vacant days to Owner."),
        Bill("HC-G-2026-03", "HC", "gas", Decimal("275.63"), *march, "HC-04 is excluded."),
        Bill("MT-W-2026-03", "MT", "water", Decimal("1204.18"), *march),
        Bill("MT-S-2026-03", "MT", "sewer", Decimal("640.77"), *march),
        Bill("MT-T-2026-03", "MT", "trash", Decimal("310.40"), *march, "Per unit. Vacant days to Owner. No extra owner percent."),
        Bill("MT-G-2026-03", "MT", "gas", Decimal("890.13"), *march, "Square footage times occupied days."),
        Bill("CS-W-2026-03", "CS", "water", Decimal("2450.29"), *march),
        Bill("CS-S-2026-03", "CS", "sewer", Decimal("1108.64"), *march),
        Bill("CS-T-2026-03", "CS", "trash", Decimal("540.00"), *march),
        Bill("CS-G-2026-03", "CS", "gas", Decimal("1673.55"), *march, "CS-12 is excluded."),
        Bill("CS-E-2026-03", "CS", "electric", Decimal("736.90"), *march, "Extra utility, split by occupant-days. Not a common-area deduction."),
        Bill("CS-E-CREDIT", "CS", "electric", Decimal("-40.00"), *march, "Seeded error: negative amount. Not allocated."),
    ]
    def rule(prop: str, utility: str, method: str = "occupant_days", owner: str = "0", partial: str = "absorb", equiv: int = 0, notes: str = "") -> Rule:
        return Rule(prop, utility, method, Decimal(owner), partial, equiv, notes)

    rules = [
        rule("HC", "water", notes="Split by occupant-days. Empty units do not create an owner charge."),
        rule("HC", "sewer"),
        rule("HC", "gas"),
        rule("HC", "trash", "per_unit", "15", "owner", notes="15% to Owner off the top. Remaining pool is per occupied day; vacant days to Owner."),
        rule("MT", "water"),
        rule("MT", "sewer"),
        rule("MT", "trash", "per_unit", "0", "owner", notes="Flat per day of occupancy. Vacant days to Owner."),
        rule("MT", "gas", "square_footage", notes="Weight = square feet times occupied days."),
        rule("CS", "water"),
        rule("CS", "sewer"),
        rule("CS", "trash", "per_unit", "0", "owner"),
        rule("CS", "gas"),
        rule("CS", "electric", notes="Shown as the extra utility type."),
    ]
    return Dataset(properties, units, occupancy, bills, rules)


def _dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def _print_reconcile() -> None:
    data = demo_dataset()
    print(f"{'Bill':<16} {'Included':<10} {'Bill':>12} {'Tenants':>12} {'Owner':>12} {'Diff':>10}")
    for bill in allocate_dataset(data).bills:
        diff = bill.amount_cents - bill.tenant_cents - bill.owner_cents if bill.included else 0
        print(
            f"{bill.bill_id:<16} {('yes' if bill.included else 'no'):<10} "
            f"{_dollars(bill.amount_cents):>12} {_dollars(bill.tenant_cents):>12} "
            f"{_dollars(bill.owner_cents):>12} {_dollars(diff):>10}"
        )
    print()
    for item in collect_exceptions(data):
        where = " ".join(part for part in (item.bill_id, item.unit_id, item.property_id, item.utility) if part)
        print(f"[{item.code}] {where}: {item.message}")


def _print_explain(bill_id: str, unit_id: str) -> None:
    data = demo_dataset()
    result = next(bill for bill in allocate_dataset(data).bills if bill.bill_id == bill_id)
    line = explain_unit(data, bill_id, unit_id)
    print(f"{bill_id} / {unit_id}")
    print(f"  included:           {result.included}")
    print(f"  bill:               {_dollars(result.amount_cents)}")
    print(f"  owner off the top:  {_dollars(result.owner_pct_cents)}")
    print(f"  pool:               {_dollars(result.pool_cents)}")
    print(f"  occupant-days:      {line.occupant_days}")
    print(f"  occupied days:      {line.occupied_days}")
    print(f"  tenant weight:      {line.tenant_weight}")
    print(f"  owner weight:       {line.owner_weight}")
    print(f"  excluded:           {line.excluded}")
    print(f"  tenant gross:       {_dollars(line.tenant_gross_cents)}")
    print(f"  discount:           {_dollars(line.discount_cents)}")
    print(f"  amount due:         {_dollars(line.tenant_net_cents)}")
    print(f"  owner on this unit: {_dollars(line.owner_gross_cents + line.discount_cents)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain or reconcile the synthetic RUBS demo.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reconcile", help="Print every demo bill and the exception list.")
    explain = sub.add_parser("explain", help="Print one unit's charge on one bill.")
    explain.add_argument("bill_id")
    explain.add_argument("unit_id")
    args = parser.parse_args(argv)
    if args.command == "reconcile":
        _print_reconcile()
    else:
        _print_explain(args.bill_id, args.unit_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
