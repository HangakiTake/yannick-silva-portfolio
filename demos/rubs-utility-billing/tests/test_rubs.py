"""Reference-engine tests for the RUBS allocation model.

T1 reconciliation, the manual trace, and exception rules are pinned here.
Workbook parity (LibreOffice) lives in test_workbook.py.
"""

from datetime import date
from decimal import Decimal

import pytest

from rubs import (
    Bill,
    Dataset,
    Occupancy,
    Property,
    Rule,
    Unit,
    allocate_dataset,
    collect_exceptions,
    demo_dataset,
    explain_unit,
    money_to_cents,
    overlap_days,
    percent_of_cents,
)


def _d(value: str) -> Decimal:
    return Decimal(value)


def _property() -> Property:
    return Property("HC", "Harbor Court", "100 Harbor Lane", "Port Elm")


def _rule(**overrides) -> Rule:
    base = dict(
        property_id="HC",
        utility="water",
        method="occupant_days",
        owner_paid_points=_d("0"),
        partial_vacancy="absorb",
        vacant_equivalent=0,
    )
    base.update(overrides)
    return Rule(**base)


def _bill(**overrides) -> Bill:
    base = dict(
        bill_id="HC-W-2026-03",
        property_id="HC",
        utility="water",
        amount=_d("100.00"),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    base.update(overrides)
    return Bill(**base)


def _unit(unit_id, **overrides) -> Unit:
    base = dict(
        unit_id=unit_id,
        property_id="HC",
        is_vacant=False,
        discount_points=_d("0"),
        sqft=None,
        exclude_utilities=(),
    )
    base.update(overrides)
    return Unit(**base)


def _occ(occ_id, unit_id, occupants, move_in, move_out=None) -> Occupancy:
    return Occupancy(occ_id, unit_id, occupants, move_in, move_out)


def _dataset(units, occs, bills=None, rules=None, **kwargs) -> Dataset:
    return Dataset(
        properties=[_property()],
        units=units,
        occupancy=occs,
        bills=bills or [_bill()],
        rules=rules or [_rule()],
    )


def _by_unit(result, bill_id="HC-W-2026-03"):
    bill = next(b for b in result.bills if b.bill_id == bill_id)
    return bill, {line.unit_id: line for line in bill.lines}


def test_overlap_days_are_inclusive():
    assert overlap_days(date(2026, 3, 1), None, date(2026, 3, 1), date(2026, 3, 31)) == 31
    assert overlap_days(date(2026, 3, 16), None, date(2026, 3, 1), date(2026, 3, 31)) == 16
    assert overlap_days(date(2026, 3, 31), None, date(2026, 3, 1), date(2026, 3, 31)) == 1
    assert overlap_days(date(2025, 1, 1), date(2026, 3, 1), date(2026, 3, 1), date(2026, 3, 31)) == 1
    assert overlap_days(date(2025, 1, 1), date(2026, 2, 28), date(2026, 3, 1), date(2026, 3, 31)) == 0
    assert overlap_days(date(2026, 4, 1), None, date(2026, 3, 1), date(2026, 3, 31)) == 0


def test_percent_of_cents_uses_half_up_basis_points():
    assert money_to_cents(_d("412.37")) == 41237
    assert money_to_cents(_d("0.01")) == 1
    assert percent_of_cents(16000, 1500) == 2400  # 15% of $160
    assert percent_of_cents(10, 1500) == 2  # 1.5 cents rounds half up to 2
    assert percent_of_cents(1, 1500) == 0
    assert percent_of_cents(334, 1000) == 33  # 10% of 334 cents = 33.4 -> 33


def test_largest_remainder_three_equal_weights_pins_the_odd_cent():
    units = [_unit("HC-02"), _unit("HC-01"), _unit("HC-03")]
    occs = [
        _occ("a", "HC-01", 1, date(2026, 3, 1)),
        _occ("b", "HC-02", 1, date(2026, 3, 1)),
        _occ("c", "HC-03", 1, date(2026, 3, 1)),
    ]
    bill, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("10.00"))])))
    assert lines["HC-01"].tenant_net_cents == 334
    assert lines["HC-02"].tenant_net_cents == 333
    assert lines["HC-03"].tenant_net_cents == 333
    assert bill.tenant_cents + bill.owner_cents == 1000


def test_mid_month_move_in_is_prorated_by_inclusive_days():
    # 2 people all month (62 occupant-days) and 1 person for 16 days.
    # $78.00 makes each occupant-day worth exactly $1.00.
    units = [_unit("HC-01"), _unit("HC-02")]
    occs = [
        _occ("a", "HC-01", 2, date(2025, 1, 1)),
        _occ("b", "HC-02", 1, date(2026, 3, 16)),
    ]
    _, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("78.00"))])))
    assert lines["HC-01"].occupant_days == 62
    assert lines["HC-02"].occupant_days == 16
    assert lines["HC-01"].tenant_net_cents == 6200
    assert lines["HC-02"].tenant_net_cents == 1600


def test_vacant_unit_does_not_take_a_tenant_share_when_vacancy_is_absorbed():
    units = [_unit("HC-01"), _unit("HC-03", is_vacant=True)]
    occs = [_occ("a", "HC-01", 2, date(2025, 1, 1))]
    bill, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("50.00"))])))
    assert lines["HC-03"].tenant_net_cents == 0
    assert lines["HC-03"].owner_gross_cents == 0
    assert lines["HC-01"].tenant_net_cents == 5000
    assert bill.owner_cents == 0


def test_excluded_service_is_left_out_of_the_denominator():
    units = [
        _unit("HC-01"),
        _unit("HC-04", exclude_utilities=("gas",)),
    ]
    occs = [
        _occ("a", "HC-01", 1, date(2026, 3, 1)),
        _occ("b", "HC-04", 3, date(2026, 3, 1)),
    ]
    bill, lines = _by_unit(
        allocate_dataset(
            _dataset(
                units,
                occs,
                bills=[_bill(bill_id="HC-G", utility="gas", amount=_d("40.00"))],
                rules=[_rule(utility="gas")],
            )
        ),
        "HC-G",
    )
    assert lines["HC-04"].excluded is True
    assert lines["HC-04"].tenant_net_cents == 0
    assert lines["HC-01"].tenant_net_cents == 4000
    assert bill.tenant_cents + bill.owner_cents == 4000


def test_discount_is_deducted_from_the_tenant_and_added_to_owner():
    units = [_unit("HC-01", discount_points=_d("10")), _unit("HC-02")]
    occs = [
        _occ("a", "HC-01", 1, date(2026, 3, 1)),
        _occ("b", "HC-02", 1, date(2026, 3, 1)),
    ]
    bill, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("10.00"))])))
    # Equal split of 1000 cents is 500 / 500. 10% of 500 = 50 exactly.
    assert lines["HC-01"].tenant_gross_cents == 500
    assert lines["HC-01"].discount_cents == 50
    assert lines["HC-01"].tenant_net_cents == 450
    assert lines["HC-02"].tenant_net_cents == 500
    assert bill.owner_cents == 50
    assert bill.tenant_cents + bill.owner_cents == 1000


def test_owner_percent_comes_off_the_top_before_the_split():
    units = [_unit("HC-01"), _unit("HC-02")]
    occs = [
        _occ("a", "HC-01", 1, date(2026, 3, 1)),
        _occ("b", "HC-02", 1, date(2026, 3, 1)),
    ]
    rules = [_rule(utility="trash", owner_paid_points=_d("15"))]
    bill, lines = _by_unit(
        allocate_dataset(
            _dataset(
                units,
                occs,
                bills=[_bill(bill_id="HC-T", utility="trash", amount=_d("160.00"))],
                rules=rules,
            )
        ),
        "HC-T",
    )
    assert bill.owner_pct_cents == 2400
    assert bill.pool_cents == 13600
    assert lines["HC-01"].tenant_net_cents == 6800
    assert lines["HC-02"].tenant_net_cents == 6800
    assert bill.owner_cents == 2400
    assert bill.tenant_cents + bill.owner_cents == 16000


def test_per_unit_partial_vacancy_and_full_vacancy_go_to_owner():
    units = [_unit("HC-01"), _unit("HC-02"), _unit("HC-03", is_vacant=True)]
    occs = [
        _occ("a", "HC-01", 4, date(2026, 3, 1)),  # full 31 days
        _occ("b", "HC-02", 1, date(2026, 3, 16)),  # 16 occupied days, 15 vacant
    ]
    rules = [_rule(utility="trash", method="per_unit", partial_vacancy="owner")]
    bill, lines = _by_unit(
        allocate_dataset(
            _dataset(
                units,
                occs,
                bills=[_bill(bill_id="HC-T", utility="trash", amount=_d("93.00"))],
                rules=rules,
            )
        ),
        "HC-T",
    )
    # Weights: 31 tenant + 16 tenant + 15 owner + 31 owner = 93. $93 => $1 per day.
    assert lines["HC-01"].occupied_days == 31
    assert lines["HC-01"].tenant_net_cents == 3100
    assert lines["HC-02"].occupied_days == 16
    assert lines["HC-02"].tenant_net_cents == 1600
    assert lines["HC-02"].owner_gross_cents == 1500
    assert lines["HC-03"].tenant_net_cents == 0
    assert lines["HC-03"].owner_gross_cents == 3100
    assert bill.owner_cents == 4600
    assert bill.tenant_cents + bill.owner_cents == 9300


def test_square_footage_weights_use_occupied_days():
    units = [_unit("HC-01", sqft=100), _unit("HC-02", sqft=300)]
    occs = [
        _occ("a", "HC-01", 9, date(2026, 3, 1)),
        _occ("b", "HC-02", 1, date(2026, 3, 16)),  # 16 days * 300 sqft
    ]
    rules = [_rule(utility="gas", method="square_footage")]
    _, lines = _by_unit(
        allocate_dataset(
            _dataset(
                units,
                occs,
                bills=[_bill(bill_id="HC-G", utility="gas", amount=_d("79.00"))],
                rules=rules,
            )
        ),
        "HC-G",
    )
    # Weights 100*31=3100 and 300*16=4800, total 7900. $79 => 1 cent per weight.
    assert lines["HC-01"].tenant_weight == 3100
    assert lines["HC-02"].tenant_weight == 4800
    assert lines["HC-01"].tenant_net_cents == 3100
    assert lines["HC-02"].tenant_net_cents == 4800


def test_vacant_flag_wins_over_a_conflicting_occupancy_record():
    units = [_unit("HC-03", is_vacant=True), _unit("HC-01")]
    occs = [
        _occ("bad", "HC-03", 2, date(2026, 3, 1)),
        _occ("a", "HC-01", 1, date(2026, 3, 1)),
    ]
    bill, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("30.00"))])))
    assert lines["HC-03"].occupant_days == 0
    assert lines["HC-03"].tenant_net_cents == 0
    assert lines["HC-01"].tenant_net_cents == 3000
    assert bill.tenant_cents + bill.owner_cents == 3000
    codes = {item.code for item in collect_exceptions(_dataset(units, occs))}
    assert "vacant_has_occupancy" in codes


def test_negative_bill_is_not_allocated_and_is_flagged():
    bills = [_bill(bill_id="BAD", amount=_d("-40.00"))]
    result = allocate_dataset(_dataset([_unit("HC-01")], [_occ("a", "HC-01", 1, date(2026, 3, 1))], bills=bills))
    assert result.bills[0].included is False
    assert result.bills[0].tenant_cents == 0
    assert result.bills[0].owner_cents == 0
    codes = {item.code for item in collect_exceptions(_dataset([_unit("HC-01")], [], bills=bills))}
    assert "negative_bill" in codes


def test_service_period_gap_is_flagged_and_both_bills_still_tie():
    bills = [
        _bill(bill_id="FEB", amount=_d("26.00"), period_start=date(2026, 2, 1), period_end=date(2026, 2, 26)),
        _bill(bill_id="MAR", amount=_d("31.00"), period_start=date(2026, 3, 1), period_end=date(2026, 3, 31)),
    ]
    data = _dataset([_unit("HC-01")], [_occ("a", "HC-01", 1, date(2025, 1, 1))], bills=bills)
    gaps = [item for item in collect_exceptions(data) if item.code == "period_gap"]
    assert len(gaps) == 1
    assert "2026-02-27" in gaps[0].message
    assert "2026-02-28" in gaps[0].message
    result = allocate_dataset(data)
    for bill in result.bills:
        assert bill.included is True
        assert bill.tenant_cents + bill.owner_cents == bill.amount_cents


def test_overlapping_occupancy_is_flagged():
    occs = [
        _occ("a", "HC-01", 2, date(2026, 3, 1), date(2026, 3, 20)),
        _occ("b", "HC-01", 1, date(2026, 3, 10), date(2026, 3, 31)),
    ]
    codes = {item.code for item in collect_exceptions(_dataset([_unit("HC-01")], occs))}
    assert "occupancy_overlap" in codes


def test_no_eligible_weight_assigns_the_whole_bill_to_owner():
    units = [_unit("HC-01", is_vacant=True), _unit("HC-02", exclude_utilities=("water",))]
    data = _dataset(units, [_occ("a", "HC-02", 2, date(2026, 3, 1))], bills=[_bill(amount=_d("12.34"))])
    bill = allocate_dataset(data).bills[0]
    assert bill.tenant_cents == 0
    assert bill.owner_cents == 1234
    assert bill.tenant_cents + bill.owner_cents == bill.amount_cents
    assert "no_eligible_weight" in {item.code for item in collect_exceptions(data)}


def test_hundred_percent_owner_paid_and_hundred_percent_discount_still_tie():
    units = [_unit("HC-01", discount_points=_d("100"))]
    occs = [_occ("a", "HC-01", 1, date(2026, 3, 1))]
    rules = [_rule(owner_paid_points=_d("100"))]
    bill, lines = _by_unit(allocate_dataset(_dataset(units, occs, rules=rules, bills=[_bill(amount=_d("20.00"))])))
    assert lines["HC-01"].tenant_net_cents == 0
    assert bill.owner_cents == 2000
    assert bill.tenant_cents + bill.owner_cents == 2000


def test_one_cent_bill_goes_to_the_lowest_unit_id():
    units = [_unit("HC-03"), _unit("HC-01"), _unit("HC-02")]
    occs = [_occ(u.unit_id, u.unit_id, 1, date(2026, 3, 1)) for u in units]
    _, lines = _by_unit(allocate_dataset(_dataset(units, occs, bills=[_bill(amount=_d("0.01"))])))
    assert lines["HC-01"].tenant_net_cents == 1
    assert lines["HC-02"].tenant_net_cents == 0
    assert lines["HC-03"].tenant_net_cents == 0


def test_sequential_stints_add_days_without_an_overlap_flag():
    occs = [
        _occ("a", "HC-02", 2, date(2026, 3, 1), date(2026, 3, 12)),
        _occ("b", "HC-02", 1, date(2026, 3, 20)),
    ]
    data = _dataset([_unit("HC-02")], occs, bills=[_bill(amount=_d("24.00"))])
    assert "occupancy_overlap" not in {item.code for item in collect_exceptions(data)}
    _, lines = _by_unit(allocate_dataset(data))
    assert lines["HC-02"].occupant_days == 2 * 12 + 1 * 12
    assert lines["HC-02"].occupied_days == 24
    assert lines["HC-02"].tenant_net_cents == 2400


def test_zero_dollar_bill_ties():
    data = _dataset([_unit("HC-01")], [_occ("a", "HC-01", 1, date(2026, 3, 1))], bills=[_bill(amount=_d("0.00"))])
    bill = allocate_dataset(data).bills[0]
    assert bill.included is True
    assert bill.tenant_cents + bill.owner_cents == 0


def test_explain_unit_matches_allocation_for_every_demo_line():
    data = demo_dataset()
    result = allocate_dataset(data)
    checked = 0
    for bill in result.bills:
        if not bill.included:
            continue
        for line in bill.lines:
            trace = explain_unit(data, bill.bill_id, line.unit_id)
            assert trace.tenant_net_cents == line.tenant_net_cents
            assert trace.discount_cents == line.discount_cents
            assert trace.owner_gross_cents == line.owner_gross_cents
            checked += 1
    assert checked > 100


def test_demo_reconciles_to_the_cent_for_every_included_bill():
    result = allocate_dataset(demo_dataset())
    included = [bill for bill in result.bills if bill.included]
    assert len(included) >= 14
    for bill in included:
        assert bill.tenant_cents + bill.owner_cents == bill.amount_cents
    excluded = [bill for bill in result.bills if not bill.included]
    assert any(bill.amount_cents < 0 for bill in excluded)


def test_demo_contains_the_messy_situations_from_the_brief():
    data = demo_dataset()
    assert [len([u for u in data.units if u.property_id == pid]) for pid in ("HC", "MT", "CS")] == [4, 8, 12]
    assert any(u.is_vacant for u in data.units)
    assert any(o.move_in == date(2026, 3, 16) for o in data.occupancy)
    assert any("gas" in u.exclude_utilities for u in data.units)
    assert any(u.discount_points == _d("10") for u in data.units)
    assert any(r.utility == "trash" and r.owner_paid_points == _d("15") for r in data.rules)


def test_demo_flags_the_three_seeded_errors_and_no_reconciliation_break():
    data = demo_dataset()
    issues = collect_exceptions(data)
    codes = {item.code for item in issues}
    assert "negative_bill" in codes
    assert "vacant_has_occupancy" in codes
    assert "period_gap" in codes
    # The seeded vacant row is HC-03 and the gap is Harbor Court water.
    assert any(item.code == "vacant_has_occupancy" and item.unit_id == "HC-03" for item in issues)
    assert any(item.code == "period_gap" and item.property_id == "HC" and item.utility == "water" for item in issues)
    result = allocate_dataset(data)
    assert all(bill.tenant_cents + bill.owner_cents == bill.amount_cents for bill in result.bills if bill.included)


def test_changing_occupants_or_owner_percent_changes_the_charge():
    data = demo_dataset()
    base = allocate_dataset(data)
    water = next(b for b in base.bills if b.bill_id == "HC-W-2026-03")
    base_net = next(line.tenant_net_cents for line in water.lines if line.unit_id == "HC-01")

    more = []
    for occ in data.occupancy:
        if occ.occupancy_id == "HC-01-RES":
            more.append(Occupancy(occ.occupancy_id, occ.unit_id, occ.occupants + 3, occ.move_in, occ.move_out, occ.notes))
        else:
            more.append(occ)
    bumped = allocate_dataset(
        Dataset(data.properties, data.units, more, data.bills, data.rules)
    )
    bumped_net = next(
        line.tenant_net_cents
        for line in next(b for b in bumped.bills if b.bill_id == "HC-W-2026-03").lines
        if line.unit_id == "HC-01"
    )
    assert bumped_net > base_net

    rules = []
    for rule in data.rules:
        if rule.property_id == "HC" and rule.utility == "trash":
            rules.append(
                Rule(
                    rule.property_id,
                    rule.utility,
                    rule.method,
                    _d("40"),
                    rule.partial_vacancy,
                    rule.vacant_equivalent,
                    rule.notes,
                )
            )
        else:
            rules.append(rule)
    higher_owner = allocate_dataset(Dataset(data.properties, data.units, data.occupancy, data.bills, rules))
    trash_before = next(b for b in base.bills if b.bill_id == "HC-T-2026-03")
    trash_after = next(b for b in higher_owner.bills if b.bill_id == "HC-T-2026-03")
    assert trash_after.owner_cents > trash_before.owner_cents
    assert trash_after.tenant_cents < trash_before.tenant_cents
    assert trash_after.tenant_cents + trash_after.owner_cents == trash_after.amount_cents


def test_a_bill_does_not_leak_onto_another_propertys_units():
    result = allocate_dataset(demo_dataset())
    units = {u.unit_id: u.property_id for u in demo_dataset().units}
    for bill in result.bills:
        for line in bill.lines:
            if line.tenant_net_cents or line.owner_gross_cents or line.discount_cents:
                assert units[line.unit_id] == bill.property_id


def test_blank_move_in_contributes_no_days_and_is_flagged():
    data = _dataset(
        [_unit("HC-01")],
        [_occ("a", "HC-01", 2, None)],
        bills=[_bill(amount=_d("30.00"))],
    )
    bill = allocate_dataset(data).bills[0]
    assert bill.lines[0].occupant_days == 0
    assert bill.tenant_cents == 0
    assert bill.owner_cents == 3000
    assert any(item.code == "bad_occupancy" for item in collect_exceptions(data))


def test_unusable_rule_is_not_allocated():
    units = [_unit("HC-01"), _unit("HC-02")]
    occs = [_occ("a", "HC-01", 1, date(2026, 3, 1)), _occ("b", "HC-02", 1, date(2026, 3, 1))]
    too_high = _dataset(units, occs, rules=[_rule(owner_paid_points=_d("150"))])
    bill = allocate_dataset(too_high).bills[0]
    assert bill.included is False
    assert bill.tenant_cents == 0
    assert bill.owner_cents == 0
    assert any(item.code == "bad_owner_pct" for item in collect_exceptions(too_high))

    negative_equivalent = _dataset(units, occs, rules=[_rule(vacant_equivalent=-1)])
    skipped = allocate_dataset(negative_equivalent).bills[0]
    assert skipped.included is False
    assert any(item.code == "bad_vacant_equivalent" for item in collect_exceptions(negative_equivalent))


def test_duplicate_rule_is_flagged_and_the_first_rule_allocates():
    units = [_unit("HC-01")]
    occs = [_occ("a", "HC-01", 1, date(2026, 3, 1))]
    rules = [_rule(owner_paid_points=_d("0")), _rule(owner_paid_points=_d("50"))]
    data = _dataset(units, occs, rules=rules)
    assert any(item.code == "duplicate_rule" for item in collect_exceptions(data))
    bill = allocate_dataset(data).bills[0]
    assert bill.owner_pct_cents == 0
    assert bill.tenant_cents == 10000


def test_invalid_period_and_bad_owner_percent_are_flagged():
    bills = [_bill(period_start=date(2026, 3, 31), period_end=date(2026, 3, 1))]
    rules = [_rule(owner_paid_points=_d("150"))]
    data = _dataset([_unit("HC-01")], [], bills=bills, rules=rules)
    codes = {item.code for item in collect_exceptions(data)}
    assert "invalid_period" in codes
    assert "bad_owner_pct" in codes
