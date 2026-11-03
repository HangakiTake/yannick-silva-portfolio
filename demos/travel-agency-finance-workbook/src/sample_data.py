"""Fictional sample data for the travel agency finance workbook (deterministic).
All company and person names are invented."""
import random, datetime as dt

D = dt.date
BAM_PEG = 1.95583
ASOF = D(2026, 10, 31)
FIRST_MONTH = D(2026, 8, 1)

CUSTOMERS = [  # id, name, country, terms days
    ("C01", "Nordlicht Reisen (fictional)", "DE", 30), ("C02", "Tulipa Tours (fictional)", "NL", 30),
    ("C03", "Viaggi Aurora (fictional)", "IT", 45), ("C04", "Bosphorus Bridge Travel (fictional)", "TR", 30),
    ("C05", "Lakeside Journeys (fictional)", "GB", 30), ("C06", "Alpenrose Touristik (fictional)", "AT", 30),
    ("C07", "Fjordway Trips (fictional)", "NO", 30), ("C08", "Iberia Sol Viajes (fictional)", "ES", 45),
    ("C09", "Maple Leaf Escapes (fictional)", "CA", 30), ("C10", "Liberty Trail Travel (fictional)", "US", 30),
    ("C11", "Danube Pearl Agency (fictional)", "HU", 30), ("C12", "Baltic Amber Tours (fictional)", "LT", 30),
]
SUPPLIERS = [
    ("S01", "Hotel Stari Grad (fictional)", "Hotel", "BA"), ("S02", "Hotel Neretva View (fictional)", "Hotel", "BA"),
    ("S03", "Adriatic Coast Hotel (fictional)", "Hotel", "HR"), ("S04", "Boka Bay Suites (fictional)", "Hotel", "ME"),
    ("S05", "Hotel Kalemegdan Park (fictional)", "Hotel", "RS"), ("S06", "Ohrid Lakeview Inn (fictional)", "Hotel", "MK"),
    ("S07", "BalkanBus Coaches (fictional)", "Transport", "BA"), ("S08", "Coastline Transfers (fictional)", "Transport", "HR"),
    ("S09", "Drina Rafting Club (fictional)", "Activity", "BA"), ("S10", "Old Bridge Guides (fictional)", "Guide", "BA"),
    ("S11", "Dalmatia Guides Co (fictional)", "Guide", "HR"), ("S12", "Mountain Lodge Jahorina (fictional)", "Hotel", "BA"),
    ("S13", "Plitvice Park Tickets (fictional)", "Activity", "HR"), ("S14", "Kotor Boat Trips (fictional)", "Activity", "ME"),
    ("S15", "Global Air Desk (fictional, USD)", "Transport", "US"),
]
SALES = ["Amra K.", "Dino H.", "Lejla M."]
DESTS = ["Sarajevo", "Mostar", "Dubrovnik", "Kotor", "Belgrade", "Ohrid", "Plitvice", "Jahorina"]
DEST_SUPP = {"Sarajevo": ["S01", "S10", "S09"], "Mostar": ["S02", "S10"], "Dubrovnik": ["S03", "S08", "S11"],
             "Kotor": ["S04", "S14"], "Belgrade": ["S05"], "Ohrid": ["S06"], "Plitvice": ["S13", "S08"],
             "Jahorina": ["S12"]}


def rates():
    """Weekly USD per EUR from 2026-07-27; BAM is the fixed peg (handled in Settings)."""
    r = random.Random(7); out = []; d = D(2026, 5, 4); v = 1.0950
    while d <= D(2026, 11, 30):
        out.append((d, round(v, 4))); v += r.uniform(-0.008, 0.008); d += dt.timedelta(days=7)
    return out


def generate(n_bookings=40, seed=42, start_id=1001, months=3):
    r = random.Random(seed)
    bookings, invoices, bills, pays, exps = [], [], [], [], []
    inv_n, bill_n, pay_n = 5001, 7001, 9001
    span = 31 * months
    for i in range(n_bookings):
        bid = f"B-{start_id + i}"
        typ = "Group" if r.random() < 0.35 else "FIT"
        cust = CUSTOMERS[r.randrange(len(CUSTOMERS))]
        dest = DESTS[r.randrange(len(DESTS))]
        start = FIRST_MONTH + dt.timedelta(days=r.randrange(span - 5)) if months <= 3 else FIRST_MONTH + dt.timedelta(days=r.randrange(330))
        nights = r.randint(2, 7)
        end = start + dt.timedelta(days=nights)
        bdate = start - dt.timedelta(days=r.randint(15, 60))
        pax = r.randint(12, 40) if typ == "Group" else r.randint(1, 4)
        ccy = "USD" if cust[2] in ("US", "CA") else ("BAM" if r.random() < 0.1 else "EUR")
        status = "Cancelled" if r.random() < 0.08 else ("Completed" if end < ASOF else "Confirmed")
        cost_total = 0.0; nb = []
        for s in r.sample(DEST_SUPP[dest], min(len(DEST_SUPP[dest]), r.randint(1, 3))):
            sccy = "BAM" if s in ("S01", "S02", "S07", "S09", "S10", "S12") and r.random() < 0.6 else "EUR"
            amt = round(pax * nights * r.uniform(18, 45) if s not in ("S09", "S10", "S11", "S13", "S14") else pax * r.uniform(15, 40), 2)
            amt_ccy = round(amt * (BAM_PEG if sccy == "BAM" else 1), 2)
            bd = start - dt.timedelta(days=r.randint(0, 10))
            nb.append([f"BILL-{bill_n}", s, bid, bd, bd + dt.timedelta(days=30), "Service", sccy, amt_ccy]); bill_n += 1
            cost_total += amt
        if r.random() < 0.15:  # USD flight bill on a EUR booking (messy case)
            amt = round(pax * r.uniform(60, 120), 2)
            nb.append([f"BILL-{bill_n}", "S15", bid, bdate, bdate + dt.timedelta(days=14), "Flights", "USD", amt]); bill_n += 1
            cost_total += amt / 1.1
        sell_eur = cost_total * r.uniform(1.12, 1.32)
        sell = round(sell_eur * {"EUR": 1, "BAM": BAM_PEG, "USD": 1.1}[ccy], 2)
        bookings.append([bid, typ, cust[0], dest, SALES[r.randrange(3)], bdate, start, end, pax, status, ccy, sell])
        bills += nb
        if status != "Cancelled":
            parts = [0.3, 0.7] if typ == "Group" else [1.0]
            dates = [bdate, start - dt.timedelta(days=14)] if typ == "Group" else [bdate]
            acc = 0
            for k, (p, idt) in enumerate(zip(parts, dates)):
                a = round(sell * p, 2) if k < len(parts) - 1 else round(sell - acc, 2)
                acc += a
                invoices.append([f"INV-{inv_n}", bid, idt, idt + dt.timedelta(days=cust[3]), ccy, a]); inv_n += 1
    # payments in: most paid, some partial, some open
    for inv in invoices:
        due_passed = inv[3] < ASOF
        x = r.random()
        if (due_passed and x < 0.82) or (not due_passed and x < 0.3):
            pd = inv[2] + dt.timedelta(days=r.randint(5, 35 if due_passed else 10))
            if pd <= ASOF:
                pays.append([f"PAY-{pay_n}", pd, "In", inv[0], inv[4], inv[5], "Bank transfer", ""]); pay_n += 1
        elif x < 0.92:
            pd = inv[2] + dt.timedelta(days=r.randint(3, 20))
            if pd <= ASOF:
                pays.append([f"PAY-{pay_n}", pd, "In", inv[0], inv[4], round(inv[5] * 0.5, 2), "Bank transfer", "partial"]); pay_n += 1
    for b in bills:
        if (b[4] < ASOF and r.random() < 0.85) or r.random() < 0.25:
            pd = b[3] + dt.timedelta(days=r.randint(3, 35))
            if pd <= ASOF:
                pays.append([f"PAY-{pay_n}", pd, "Out", b[0], b[6], b[7], "Bank transfer", ""]); pay_n += 1
    cats = [("Rent", 900), ("Salaries", 3900), ("Software", 240), ("Marketing", 450), ("Utilities", 180), ("Bank fees", 60)]
    e = 1
    for m in range(months):
        md = D(FIRST_MONTH.year + (FIRST_MONTH.month - 1 + m) // 12, (FIRST_MONTH.month - 1 + m) % 12 + 1, 1)
        for c, base in cats:
            ccy = "BAM" if c in ("Rent", "Salaries", "Utilities") else "EUR"
            amt = round(base * r.uniform(0.9, 1.1) * (BAM_PEG if ccy == "BAM" else 1), 2)
            exps.append([f"EXP-{e:04d}", md + dt.timedelta(days=r.randint(0, 25)), c, f"{c} {md:%b %Y}", ccy, amt]); e += 1
    return dict(bookings=bookings, invoices=invoices, bills=bills, payments=pays, expenses=exps,
                next=dict(inv=inv_n, bill=bill_n, pay=pay_n))


def seeded_cases(data, include_over=False):
    """Overwrite/add records for scripted payment and aging tests. Returns expectations."""
    bk = [b for b in data["bookings"] if b[9] != "Cancelled"]
    n = data["next"]; inv, pays, bills = data["invoices"], data["payments"], data["bills"]
    # remove auto payments on the invoices/bills we take over
    def take_inv(k):
        target = [i for i in inv if i[1] == bk[k][0]][0]
        data["payments"][:] = [p for p in pays if p[3] != target[0]]
        return target
    exp = {}
    cases = []
    def pay(d, dirn, ref, ccy, amt, note):
        pays.append([f"PAY-{n['pay']}", d, dirn, ref, ccy, amt, "Bank transfer", note]); n["pay"] += 1
    # Use dedicated test invoices on existing bookings (extra invoices would break invoice=sell check),
    # so we modify the first invoice of selected EUR bookings.
    eur_bk = [i for i, b in enumerate(bk) if b[10] == "EUR"]
    T = [take_inv(k) for k in eur_bk[:8]]
    for t in T: t[4] = "EUR"
    pd_ = lambda t: min(t[2] + dt.timedelta(days=3), ASOF)
    D0 = pd_(T[0])
    a = T[0][5]; pay(D0, "In", T[0][0], "EUR", a, "T1 single full"); cases.append(("T1 one full payment", T[0][0], 0.0))
    D0 = pd_(T[1]); a = T[1][5]; p1, p2 = round(a * .3, 2), round(a * .3, 2); p3 = round(a * .1, 2)
    for p in (p1, p2, p3): pay(D0, "In", T[1][0], "EUR", p, "T2 partial")
    cases.append(("T2 three partials (70%)", T[1][0], round(a - p1 - p2 - p3, 2)))
    D0 = pd_(T[2]); a = T[2][5]
    if include_over:  # test copy only: the shipped sample stays clean (Checks = ALL OK)
        pay(D0, "In", T[2][0], "EUR", round(a + 100, 2), "T3 overpayment"); cases.append(("T3 overpayment flagged", T[2][0], -100.0))
    else:
        pay(D0, "In", T[2][0], "EUR", a, "full")
    D0 = pd_(T[3]); a = T[3][5]; pay(D0, "In", T[3][0], "BAM", round(a * BAM_PEG, 2), "T4 paid in BAM"); cases.append(("T4 EUR invoice paid in BAM", T[3][0], round(a - round(a * BAM_PEG, 2) / BAM_PEG, 2)))
    D0 = pd_(T[4]); a = T[4][5]; u = round(a * 0.4 * 1.1, 2)
    pay(D0, "In", T[4][0], "USD", u, "T5 USD part"); cases.append(("T5 EUR invoice part-paid in USD", T[4][0], ("usd", a, u, D0)))
    D0 = pd_(T[5]); a = T[5][5]; pay(D0, "In", T[5][0], "EUR", round(a + 150, 2), "T6 paid 150 too much"); pay(min(D0 + dt.timedelta(days=5), ASOF), "In", T[5][0], "EUR", -150.0, "T6 refund of excess"); cases.append(("T6 overpaid then refunded", T[5][0], 0.0))
    cases.append(("T7 invoice, no payment", T[6][0], T[6][5]))
    D0 = pd_(T[7]); a = T[7][5]; pay(D0, "In", T[7][0], "EUR", round(a / 2, 2), "T8 EUR half"); pay(D0, "In", T[7][0], "BAM", round((a - round(a / 2, 2)) * BAM_PEG, 2), "T8 BAM rest")
    cases.append(("T8 paid in two currencies (EUR+BAM)", T[7][0], ("two", a, round(a / 2, 2), round((a - round(a / 2, 2)) * BAM_PEG, 2))))
    # bills
    b1 = [b for b in bills if b[6] == "EUR"][0]; data["payments"][:] = [p for p in data["payments"] if p[3] != b1[0]]
    D0 = min(b1[3] + dt.timedelta(days=3), ASOF); pay(D0, "Out", b1[0], "EUR", round(b1[7] * .4, 2), "T9 partial out"); cases.append(("T9 supplier bill 40% paid", b1[0], round(b1[7] - round(b1[7] * .4, 2), 2)))
    b2 = [b for b in bills if b[6] == "USD"][0]; data["payments"][:] = [p for p in data["payments"] if p[3] != b2[0]]
    D0 = min(b2[3] + dt.timedelta(days=3), ASOF); e10 = round(b2[7] * 0.4 / 1.1, 2); pay(D0, "Out", b2[0], "EUR", e10, "T10 USD bill paid in EUR"); cases.append(("T10 USD bill part-paid in EUR", b2[0], ("usdbill", b2[7], e10, D0)))
    # aging seeds: 6 invoices + 6 bills with dates set to known ages vs ASOF (open, unpaid)
    aging = []
    ages = [10, 45, 75, 120, 30, 61]
    bucket = lambda d: "0-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"
    ai = [i for i in inv if i not in T][:6]
    for i, d in zip(ai, ages):
        data["payments"][:] = [p for p in data["payments"] if p[3] != i[0]]
        i[2] = ASOF - dt.timedelta(days=d); i[3] = i[2] + dt.timedelta(days=30); aging.append((i[0], bucket(d)))
    ab = [b for b in bills if b not in (b1, b2)][:6]
    for b, d in zip(ab, ages):
        data["payments"][:] = [p for p in data["payments"] if p[3] != b[0]]
        b[3] = ASOF - dt.timedelta(days=d); b[4] = b[3] + dt.timedelta(days=30); aging.append((b[0], bucket(d)))
    return cases, aging
