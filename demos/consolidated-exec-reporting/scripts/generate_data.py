"""Generate the synthetic sources for the demo (fictional company:
Kestrel Industrial Supplies). Deterministic: same seed -> same files.

Writes:
  data/base/      Apr-Sep 2026, with 15 seeded issues + customer-matching cases
  data/clean/     same business data, no seeded issues and no hard name variants
  data/next/      base + the Oct 2026 files (monthly refresh test, R8)
  data/messy/     base with real-world layout damage (R9)
  data/answer_key.json
"""
import csv, json, random, shutil, datetime as dt
from pathlib import Path
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1] / "data"
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
NEXT_MONTH = "2026-10"
SUFFIX = {"PL": "Sp. z o.o.", "DE": "GmbH", "AT": "GmbH", "CZ": "s.r.o.", "CH": "AG"}
COUNTRIES = ["PL"] * 50 + ["DE"] * 35 + ["AT"] * 15 + ["CZ"] * 12 + ["CH"] * 8
W1 = ["Nord", "Baltic", "Vistula", "Silesia", "Alpen", "Rhein", "Donau", "Moldau",
      "Tatra", "Oder", "Kraków", "Bavaria", "Steiner", "Müller", "Novak", "Zielin",
      "Elbe", "Inn", "Lech", "Warta", "Sudety", "Karpat", "Boden", "Jura"]
W2 = ["Metal", "Tech", "Logistik", "Bau", "Hydraulik", "Systems", "Montage",
      "Elektro", "Plast", "Werkzeug", "Stal", "Automation", "Pack", "Drive"]
OWNERS = ["A. Kowalska", "M. Nowak", "J. Wagner", "P. Huber", "K. Dvořák"]
STAGES = ["Lead"] * 4 + ["Qualified"] * 4 + ["Proposal"] * 3 + ["Negotiation"] * 2 + ["Won"] * 4 + ["Lost"] * 3


def customers(rng):
    seen, out = set(), []
    i = 1001
    for c in COUNTRIES:
        while True:
            name = f"{rng.choice(W1)} {rng.choice(W2)} {SUFFIX[c]}"
            key = (name.lower(), c)
            if key not in seen:
                seen.add(key); break
        out.append({"account_id": f"ACC-{i}", "account_name": name, "country": c,
                    "owner": rng.choice(OWNERS)})
        i += 1
    return out


def easy_variant(rng, name):
    """Variants the matching rules are designed to handle."""
    v = rng.random()
    if v < 0.55: return name
    if v < 0.65: return name.upper()
    if v < 0.72: return name.lower()
    if v < 0.82: return "  " + name.replace(" ", "  ", 1) + " "
    if v < 0.90: return name.replace("Sp. z o.o.", "Sp.z o.o.").replace("s.r.o.", "s. r. o.")
    return name.rstrip(".")


def hard_variant(name):
    """Variants a human would match but the rules deliberately do not."""
    return (name.replace("ü", "ue").replace("ó", "o").replace("Systems", "Sys.")
            .replace("Logistik", "Logistics").replace("Automation", "Autom.")
            .replace(" Sp. z o.o.", " Spółka z o.o."))


def month_dates(rng, ym, n):
    y, m = map(int, ym.split("-"))
    days = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    return sorted(dt.date(y, m, rng.randint(1, days)) for _ in range(n))


def amount(rng):
    return round(rng.lognormvariate(8.3, 0.7), 2)


def build(seed=7, seeded=True):
    rng = random.Random(seed)
    accts = customers(rng)
    pl = [a for a in accts if a["country"] == "PL"]
    dach = [a for a in accts if a["country"] != "PL"]
    key = {"seeded_issues": [], "match_truth": {}, "new_customers": [], "hard_variants": [], "duplicated_accounts": []}

    # --- CRM accounts (+2 duplicate accounts) ---
    crm_accounts = [dict(a) for a in accts]
    if seeded:
        for src, newid in ((pl[3], "ACC-1201"), (dach[5], "ACC-1202")):
            key["duplicated_accounts"].append(src["account_id"])
            crm_accounts.append({"account_id": newid, "account_name": src["account_name"].upper(),
                                 "country": src["country"], "owner": rng.choice(OWNERS)})
            key["seeded_issues"].append({"file": "crm_accounts.csv", "key": newid,
                                         "issue": "DUPLICATE_ACCOUNT"})

    # --- CRM deals (+3 unknown account ids) ---
    deals = []
    for i in range(220):
        a = rng.choice(accts)
        cur = "PLN" if a["country"] == "PL" and rng.random() < 0.7 else "EUR"
        amt = amount(rng) * (4.2 if cur == "PLN" else 1) * 3
        close = dt.date(2026, 4, 1) + dt.timedelta(days=rng.randint(0, 270))
        deals.append({"deal_id": f"D-{5000 + i}", "account_id": a["account_id"],
                      "stage": rng.choice(STAGES), "amount": f"{amt:.2f}", "currency": cur,
                      "expected_close": close.isoformat(), "owner": a["owner"]})
    if seeded:
        for j, d in enumerate(rng.sample(deals, 3)):
            d["account_id"] = f"ACC-9{j}0{j}"
            key["seeded_issues"].append({"file": "crm_deals.csv", "key": d["deal_id"],
                                         "issue": "UNKNOWN_ACCOUNT"})

    # --- invoices: 25 PL + 25 DACH per month = 300 over 6 months ---
    def invoices(months, start_no):
        rows = {"PL": {}, "DACH": {}}
        n = start_no
        for ym in months:
            for reg, pool, k in (("PL", pl, 25), ("DACH", dach, 25)):
                lst = []
                for d in month_dates(rng, ym, k):
                    a = rng.choice(pool)
                    cur = "PLN" if reg == "PL" else ("CHF" if a["country"] == "CH" else
                                                     ("CZK" if a["country"] == "CZ" and rng.random() < .5 else "EUR"))
                    amt = amount(rng) * {"PLN": 4.3, "CHF": 0.95, "CZK": 25, "EUR": 1}[cur]
                    inv = f"{'FV' if reg == 'PL' else 'RE'}/{ym.replace('-', '')}/{n:05d}"
                    n += 1
                    lst.append({"invoice_no": inv, "date": d, "acct": a, "name": easy_variant(rng, a["account_name"]),
                                "cust_id": a["account_id"] if reg == "DACH" and rng.random() < 0.7 else "",
                                "amount": round(amt, 2), "currency": cur})
                rows[reg][ym] = lst
        return rows, n

    inv, nxt = invoices(MONTHS, 1)
    inv_next, _ = invoices([NEXT_MONTH], nxt)

    if seeded:
        allrows = [(reg, ym, r) for reg in inv for ym in inv[reg] for r in inv[reg][ym]]
        picks = rng.sample(allrows, 40)
        hard = 0
        for reg, ym, r in picks:  # hard name variants (rules should NOT match these)
            if r["cust_id"] == "" and hard_variant(r["acct"]["account_name"]) != r["acct"]["account_name"] and hard < 4:
                r["name"] = hard_variant(r["acct"]["account_name"]); r["hard"] = True; hard += 1
        assert hard == 4, hard
        # 3 invoices for customers not in the CRM at all
        for j, (reg, ym, r) in enumerate([p for p in picks if not p[2].get("hard")][:3]):
            nm, ctry = (("Wisła Trade Sp. z o.o.", "PL"), ("Bałtyk Serwis Sp. z o.o.", "PL"), ("Gamma Fördertechnik GmbH", "DE"))[j] \
                if reg == "PL" else (("Gamma Fördertechnik GmbH", "DE"), ("Opava Strojírny s.r.o.", "CZ"), ("Linz Förderband GmbH", "AT"))[j]
            if reg == "PL" and ctry != "PL": nm, ctry = "Mazury Hydro Sp. z o.o.", "PL"
            r["name"], r["cust_id"], r["acct"], r["country_override"] = nm, "", None, ctry
            key["new_customers"].append(r["invoice_no"])
        free = [p for p in picks if not p[2].get("hard") and p[2]["acct"] is not None]
        it = iter(free)
        def seed(issue, fn):
            reg, ym, r = next(it); fn(reg, ym, r)
            key["seeded_issues"].append({"file": reg, "key": r["invoice_no"], "issue": issue, "month": ym})
        for _ in range(3):  # duplicates: same invoice repeated later in the same file
            def dup(reg, ym, r): inv[reg][ym].append(dict(r, dup=True))
            seed("DUPLICATE_INVOICE", dup)
        seed("BAD_DATE", lambda reg, ym, r: r.update(date="31.02.2026"))
        seed("BAD_DATE", lambda reg, ym, r: r.update(date="TBC"))
        seed("BAD_AMOUNT", lambda reg, ym, r: r.update(amount="n/a"))
        seed("BAD_AMOUNT", lambda reg, ym, r: r.update(amount="ca. 500"))
        dach_free = [p for p in free if p[0] == "DACH"]
        it = iter([p for p in dach_free if p not in free[:7]])
        seed("BAD_CURRENCY", lambda reg, ym, r: r.update(currency=""))
        seed("BAD_CURRENCY", lambda reg, ym, r: r.update(currency="USD"))
        it = iter([p for p in free[7:] if p[0] == "PL" and p not in dach_free])
        seed("DATE_OUTSIDE_FILE_MONTH", lambda reg, ym, r: r.update(date=dt.date(2027, 3, 1)))
        # a few valid PL text formats (should parse, not be flagged)
        for r in inv["PL"]["2026-06"][:4]:
            if isinstance(r["date"], dt.date) and not r.get("dup"):
                r["date"] = r["date"].strftime("%d.%m.%Y")
        for r in inv["PL"]["2026-07"][:3]:
            if isinstance(r["amount"], float) and not r.get("dup"):
                r["amount"] = f"{r['amount']:,.2f}".replace(",", " ").replace(".", ",")

    for reg in inv:
        for ym in inv[reg]:
            for r in inv[reg][ym]:
                if not r.get("dup"):
                    key["match_truth"][r["invoice_no"]] = r["acct"]["account_id"] if r["acct"] else None
                    if r.get("hard"): key["hard_variants"].append(r["invoice_no"])
    return accts, crm_accounts, deals, inv, inv_next, key


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)


def write_pl(path, rows, ym):
    wb = Workbook(); ws = wb.active; ws.title = "Sprzedaz"
    ws.append(["Nr faktury", "Data sprzedazy", "Klient", "Kraj", "Kwota netto", "Waluta"])
    for r in rows:
        ws.append([r["invoice_no"], r["date"], r["name"], r.get("country_override") or (r["acct"] or {}).get("country", "PL"),
                   r["amount"], r["currency"]])
        if isinstance(r["date"], dt.date): ws.cell(ws.max_row, 2).number_format = "DD.MM.YYYY"
    wb.save(path)


def write_dach(path, rows, ym):
    wb = Workbook(); ws = wb.active; ws.title = "Export"
    ws.append([f"Kestrel DACH - Umsatz Export {ym}"])
    ws.append(["Generated from ERP, do not edit"])
    ws.append([])
    ws.append(["Invoice No", "Cust ID", "Customer", "Country", "Invoice Date", "Net Amount", "Currency"])
    for r in rows:
        ws.append([r["invoice_no"], r["cust_id"], r["name"], r.get("country_override") or r["acct"]["country"],
                   r["date"], r["amount"], r["currency"]])
        if isinstance(r["date"], dt.date): ws.cell(ws.max_row, 5).number_format = "DD.MM.YYYY"
    wb.save(path)


def write_set(folder, crm_accounts, deals, inv, targets):
    if folder.exists(): shutil.rmtree(folder)
    (folder / "crm").mkdir(parents=True); (folder / "sales_pl").mkdir(); (folder / "sales_dach").mkdir()
    write_csv(folder / "crm" / "crm_accounts.csv", crm_accounts, ["account_id", "account_name", "country", "owner"])
    write_csv(folder / "crm" / "crm_deals.csv", deals, ["deal_id", "account_id", "stage", "amount", "currency", "expected_close", "owner"])
    write_csv(folder / "targets.csv", targets, ["month", "region", "target_eur"])
    for ym, rows in inv["PL"].items(): write_pl(folder / "sales_pl" / f"sales_pl_{ym}.xlsx", rows, ym)
    for ym, rows in inv["DACH"].items(): write_dach(folder / "sales_dach" / f"sales_dach_{ym}.xlsx", rows, ym)


def targets():
    out = []
    for i, ym in enumerate(MONTHS + [NEXT_MONTH, "2026-11", "2026-12"]):
        for reg, base in (("PL", 128000), ("DACH", 94000), ("CEE", 21000)):
            out.append({"month": f"{ym}-01", "region": reg, "target_eur": f"{base * (1 + 0.02 * i):.2f}"})
    return out


def make_messy(base, messy):
    if messy.exists(): shutil.rmtree(messy)
    shutil.copytree(base, messy)
    notes = []
    # 1 merged title row above the header + blank rows inside the data (PL Apr)
    p = messy / "sales_pl" / "sales_pl_2026-04.xlsx"
    wb = load_workbook(p); ws = wb.active
    ws.insert_rows(1); ws["A1"] = "Sprzedaż - kwiecień 2026"; ws.merge_cells("A1:F1")
    for r in (6, 12, 20): ws.insert_rows(r)
    wb.save(p); notes.append("sales_pl_2026-04.xlsx: merged title row above header, 3 blank rows")
    # 2 renamed header that IS a known alias (PL May): must load normally
    p = messy / "sales_pl" / "sales_pl_2026-05.xlsx"
    wb = load_workbook(p); ws = wb.active; ws["E1"] = "Kwota netto (PLN)"; wb.save(p)
    notes.append("sales_pl_2026-05.xlsx: header 'Kwota netto' renamed to known alias 'Kwota netto (PLN)'")
    # 3 renamed header that is NOT known (DACH Jun): must fail loudly, file skipped
    p = messy / "sales_dach" / "sales_dach_2026-06.xlsx"
    wb = load_workbook(p); ws = wb.active; ws["F4"] = "Betrag"; wb.save(p)
    notes.append("sales_dach_2026-06.xlsx: header 'Net Amount' renamed to unknown 'Betrag' -> must be rejected")
    # 4 EU number format as text (DACH Jul)
    p = messy / "sales_dach" / "sales_dach_2026-07.xlsx"
    wb = load_workbook(p); ws = wb.active; changed = 0
    for row in ws.iter_rows(min_row=5):
        c = row[5]
        if isinstance(c.value, float) and c.value >= 1000 and changed < 5:
            c.value = f"{c.value:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."); changed += 1
    wb.save(p); notes.append(f"sales_dach_2026-07.xlsx: {changed} amounts as EU text like 1.234,56")
    # 5 CRM deals exported with semicolons? keep CSV but add a blank trailing line + BOM
    p = messy / "crm" / "crm_deals.csv"
    txt = p.read_text(encoding="utf-8"); p.write_text("\ufeff" + txt + "\n\n", encoding="utf-8")
    notes.append("crm_deals.csv: UTF-8 BOM and trailing blank lines")
    return notes


def main():
    accts, crm_accounts, deals, inv, inv_next, key = build(seeded=True)
    t = targets()
    write_set(ROOT / "base", crm_accounts, deals, inv, t)
    nxt = {reg: dict(inv[reg], **inv_next[reg]) for reg in inv}
    write_set(ROOT / "next", crm_accounts, deals, nxt, t)
    _, c_accts, c_deals, c_inv, _, c_key = build(seeded=False)
    write_set(ROOT / "clean", c_accts, c_deals, c_inv, t)
    key["messy_changes"] = make_messy(ROOT / "base", ROOT / "messy")
    key["next_month"] = NEXT_MONTH
    key["next_month_rows"] = sum(len(v) for reg in inv_next for v in inv_next[reg].values())
    (ROOT / "answer_key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    print("seeded:", len(key["seeded_issues"]), "match rows:", len(key["match_truth"]))


if __name__ == "__main__":
    main()
