"""Python mirror of the Power Query logic in powerquery/*.m.

Same rules, same column order, same output tables. It exists because
Power Query cannot run on Linux: it lets the rules be tested here, and its
KPI figures are written into the workbook's Checks sheet so that, after a
Refresh All in desktop Excel, any difference between the two shows up.
"""
import csv, datetime as dt, re, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from openpyxl import load_workbook
sys.path.insert(0, str(Path(__file__).parent))
from config import FX_TO_EUR, STAGE_PROB, OPEN_STAGES, REGION, PL_ALIASES, DACH_ALIASES

ISSUE_ORDER = ["MISSING_INVOICE_NO", "DUPLICATE_INVOICE", "BAD_DATE", "BAD_AMOUNT", "BAD_CURRENCY", "DATE_OUTSIDE_FILE_MONTH"]
OPTIONAL_COLUMNS = {"customer_id"}  # DACH Cust ID: used for matching when present
EXCLUDED = set(ISSUE_ORDER) | {"BAD_STAGE", "BAD_TARGET"}


def r2(x):
    return float(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def norm_name(s):
    return "".join(ch for ch in str(s or "").casefold() if ch.isalnum())


def parse_amount(v):
    if isinstance(v, bool) or v is None: return None
    if isinstance(v, (int, float)): return float(v)
    t = str(v).replace(" ", "").replace("\u00a0", "")
    if "," in t and "." in t:  # both marks: the last one is the decimal mark
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:  # one comma + 1-2 digits = decimal comma; anything else (1,234) is ambiguous
        t = t.replace(",", ".") if re.fullmatch(r"-?\d+,\d{1,2}", t) else "ambiguous"
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):  # 1.234 = EU thousands or US decimals: ambiguous
        t = "ambiguous"
    return float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else None


def parse_date(v):
    if isinstance(v, dt.datetime): return v.date()
    if isinstance(v, dt.date): return v
    t = str(v or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try: return dt.datetime.strptime(t, fmt).date()
        except ValueError: pass
    return None


def blank(row):
    return all(c is None or str(c).strip() == "" for c in row)


def read_excel(path, aliases):
    """Return (schema_row, records). Records keep the raw-table row number."""
    ws = load_workbook(path, data_only=True).worksheets[0]
    raw = [list(r) for r in ws.iter_rows(values_only=True)]
    anchors = {a.casefold() for a in aliases["invoice_no"]}
    hdr = next((i for i, r in enumerate(raw[:10])
                if any(str(c or "").strip().casefold() in anchors for c in r)), None)
    schema = {"file": path.name, "status": "OK", "missing_columns": "", "unmapped_columns": ""}
    if hdr is None:
        schema.update(status="FAILED", missing_columns="header row not found in first 10 rows",
                      rows_read=sum(1 for r in raw if not blank(r)))
        return schema, []
    headers = [str(c or "").strip() for c in raw[hdr]]
    colmap, used = {}, set()
    for std, names in aliases.items():
        for j, h in enumerate(headers):
            if h.casefold() in {n.casefold() for n in names}:
                colmap[std] = j; used.add(j); break
    missing = [s for s in aliases if s not in colmap and s not in OPTIONAL_COLUMNS]
    schema["unmapped_columns"] = ", ".join(h for j, h in enumerate(headers) if h and j not in used)
    if missing:
        schema.update(status="FAILED", missing_columns=", ".join(missing),
                      rows_read=sum(1 for r in raw if not blank(r)))
        return schema, []
    recs = []
    for i, r in enumerate(raw[hdr + 1:], start=hdr + 2):
        if blank(r): continue
        rec = {s: r[j] if j < len(r) else None for s, j in colmap.items()}
        rec["source_row"] = i
        recs.append(rec)
    schema["rows_read"] = len(recs)
    return schema, recs


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        first = f.readline(); f.seek(0)
        delim = ";" if first.count(";") > first.count(",") else ","  # PL/DE Excel locales export with ';'
        rows = []
        for i, r in enumerate(csv.DictReader(f, delimiter=delim), start=2):  # number before dropping blanks
            if any((v or "").strip() for v in r.values() if isinstance(v, str)):
                r["source_row"] = i; rows.append(r)
    return rows


def run(folder):
    folder = Path(folder)
    accounts = read_csv(folder / "crm" / "crm_accounts.csv")
    deals_raw = read_csv(folder / "crm" / "crm_deals.csv")
    targets_raw = read_csv(folder / "targets.csv")
    exceptions, schema_rows, recon = [], [], []

    def exc(file, row, key, issue, detail, raw="", action="Excluded from figures"):
        exceptions.append({"source_file": file, "source_row": row, "record_key": key, "issue": issue,
                           "detail": detail, "amount_raw": "" if raw is None else str(raw), "action": action})

    # accounts: duplicate detection on normalised name + country
    by_id, by_name, seen = {}, {}, {}
    for a in accounts:
        by_id[a["account_id"]] = a
        k = (norm_name(a["account_name"]), a["country"].strip().upper())
        by_name.setdefault(k, []).append(a["account_id"])
        if k in seen:
            exc("crm_accounts.csv", a["source_row"], a["account_id"], "DUPLICATE_ACCOUNT",
                f"Same name and country as {seen[k]}", action="Listed; merge in CRM")
        else:
            seen[k] = a["account_id"]
    recon.append({"source_file": "crm_accounts.csv", "source": "CRM", "rows_read": len(accounts),
                  "rows_loaded": len(accounts), "rows_excluded": 0, "eur_source": 0.0, "eur_loaded": 0.0, "eur_excluded": 0.0})

    # sales files
    sales, seen_inv = [], set()
    for sub, aliases, src in (("sales_pl", PL_ALIASES, "Excel PL"), ("sales_dach", DACH_ALIASES, "Excel DACH")):
        for p in sorted((folder / sub).glob("*.xlsx")):
            if p.name.startswith("~$"): continue
            ym = re.search(r"(\d{4}-\d{2})", p.name).group(1)
            schema, recs = read_excel(p, aliases)
            schema_rows.append(schema)
            if schema["status"] != "OK":
                recon.append({"source_file": p.name, "source": "REJECTED", "rows_read": schema["rows_read"], "rows_loaded": 0, "rows_excluded": 0,
                              "eur_source": None, "eur_loaded": 0.0, "eur_excluded": 0.0})
                exc(p.name, "", p.name, "FILE_REJECTED", f"Missing required column(s): {schema['missing_columns']}",
                    action="Whole file skipped; fix header and refresh")
                continue
            loaded = excluded = 0; eur_src = eur_ld = eur_ex = 0.0
            for r in recs:
                inv = str(r["invoice_no"] or "").strip()
                d = parse_date(r["invoice_date"]); amt = parse_amount(r["amount"])
                cur = str(r.get("currency") or "").strip().upper()
                eur = r2(amt * FX_TO_EUR[cur]) if amt is not None and cur in FX_TO_EUR else None
                issue = None
                if not inv: issue = ("MISSING_INVOICE_NO", "Invoice number is blank")
                elif inv in seen_inv: issue = ("DUPLICATE_INVOICE", "Invoice number already loaded")
                elif d is None: issue = ("BAD_DATE", f"Unreadable date '{r['invoice_date']}'")
                elif amt is None: issue = ("BAD_AMOUNT", f"Amount is not a number '{r['amount']}'")
                elif cur not in FX_TO_EUR: issue = ("BAD_CURRENCY", f"Currency '{cur}' not in FX table")
                elif d.strftime("%Y-%m") != ym: issue = ("DATE_OUTSIDE_FILE_MONTH", f"Date {d.isoformat()} is not in {ym}")
                seen_inv.add(inv)
                if eur is not None: eur_src += eur
                if issue:
                    excluded += 1; eur_ex += eur or 0.0
                    exc(p.name, r["source_row"], inv, issue[0], issue[1], r["amount"]); continue
                country = str(r["country"] or "").strip().upper()
                cid = str(r.get("customer_id") or "").strip()
                name = str(r["customer_name"] or "").strip()
                if cid and cid in by_id: method, acct = "id", by_id[cid]
                else:
                    cands = by_name.get((norm_name(name), country), [])
                    if len(cands) == 1: method, acct = "name", by_id[cands[0]]
                    else:
                        method, acct = ("ambiguous" if cands else "unmatched"), None
                        exc(p.name, r["source_row"], inv, "AMBIGUOUS_CUSTOMER" if cands else "UNMATCHED_CUSTOMER",
                            (f"Name matches {len(cands)} CRM accounts" if cands else f"'{name}' ({country}) not found in CRM"),
                            r["amount"], action="Included in revenue as (unmatched); fix name or add Cust ID")
                if country not in REGION:
                    exc(p.name, r["source_row"], inv, "UNKNOWN_COUNTRY", f"Country '{country}' not in tbl_Region", r["amount"],
                        action="Included in revenue under region Other; add the country to tbl_Region")
                loaded += 1; eur_ld += eur
                sales.append({"invoice_no": inv, "source_file": p.name, "source_row": r["source_row"],
                              "invoice_date": d, "month_start": d.replace(day=1),
                              "customer_id": acct["account_id"] if acct else "",
                              "customer_name": acct["account_name"] if acct else "(unmatched) " + name,
                              "country": country, "region": REGION.get(country, "Other"),
                              "amount": amt, "currency": cur, "amount_eur": eur, "match_method": method})
            recon.append({"source_file": p.name, "source": src, "rows_read": len(recs), "rows_loaded": loaded,
                          "rows_excluded": excluded, "eur_source": r2(eur_src), "eur_loaded": r2(eur_ld), "eur_excluded": r2(eur_ex)})

    # deals
    pipeline = []; loaded = excluded = 0; eur_src = eur_ld = eur_ex = 0.0
    for d in deals_raw:
        amt = parse_amount(d["amount"]); cur = d["currency"].strip().upper(); stage = d["stage"].strip()
        eur = r2(amt * FX_TO_EUR[cur]) if amt is not None and cur in FX_TO_EUR else None
        if eur is not None: eur_src += eur
        bad = ("BAD_AMOUNT", f"Amount is not a number '{d['amount']}'") if amt is None else \
              ("BAD_CURRENCY", f"Currency '{cur}' not in FX table") if eur is None else \
              ("BAD_STAGE", f"Unknown stage '{stage}'") if stage not in STAGE_PROB else None
        if bad:
            excluded += 1; eur_ex += eur or 0.0
            exc("crm_deals.csv", d["source_row"], d["deal_id"], bad[0], bad[1], d["amount"]); continue
        a = by_id.get(d["account_id"].strip())
        if a is None:
            exc("crm_deals.csv", d["source_row"], d["deal_id"], "UNKNOWN_ACCOUNT",
                f"Account '{d['account_id']}' not in CRM accounts", d["amount"],
                action="Included in pipeline as (unknown account); fix in CRM")
        loaded += 1; eur_ld += eur
        country = a["country"].strip().upper() if a else ""
        pipeline.append({"deal_id": d["deal_id"], "account_id": d["account_id"].strip(),
                         "account_name": a["account_name"] if a else "(unknown account)",
                         "country": country, "region": REGION.get(country, "Unknown"), "stage": stage,
                         "amount": amt, "currency": cur, "amount_eur": eur, "probability": STAGE_PROB[stage],
                         "weighted_eur": r2(eur * STAGE_PROB[stage]),
                         "expected_close": parse_date(d["expected_close"]), "owner": d["owner"]})
    recon.append({"source_file": "crm_deals.csv", "source": "CRM", "rows_read": len(deals_raw), "rows_loaded": loaded,
                  "rows_excluded": excluded, "eur_source": r2(eur_src), "eur_loaded": r2(eur_ld), "eur_excluded": r2(eur_ex)})

    targets, bad_t = [], []
    for t in targets_raw:
        row = {"month_start": parse_date(t["month"]), "region": (t["region"] or "").strip(),
               "target_eur": parse_amount(t["target_eur"])}
        if row["month_start"] is None or row["target_eur"] is None or not row["region"]:
            bad_t.append(row)
            exc("targets.csv", t["source_row"], t["month"], "BAD_TARGET",
                f"Unreadable target row: month '{t['month']}', region '{row['region']}', target '{t['target_eur']}'",
                t["target_eur"], action="Excluded from targets")
        else:
            targets.append(row)
    s_ok = sum(t["target_eur"] for t in targets); s_bad = sum(t["target_eur"] or 0 for t in bad_t)
    recon.append({"source_file": "targets.csv", "source": "CSV", "rows_read": len(targets_raw), "rows_loaded": len(targets),
                  "rows_excluded": len(bad_t), "eur_source": r2(s_ok + s_bad), "eur_loaded": r2(s_ok), "eur_excluded": r2(s_bad)})
    for r in recon:
        r["row_diff"] = r["rows_read"] - r["rows_loaded"] - r["rows_excluded"]
        r["eur_diff"] = None if r["eur_source"] is None else r2(r["eur_source"] - r["eur_loaded"] - r["eur_excluded"])
    return {"sales": sales, "pipeline": pipeline, "targets": targets, "exceptions": exceptions,
            "schema": schema_rows, "recon": recon}


def kpis(out):
    """Six headline KPIs, computed from the consolidated tables."""
    s, p, t = out["sales"], out["pipeline"], out["targets"]
    latest = max(r["month_start"] for r in s)
    rev = r2(sum(r["amount_eur"] for r in s))
    tgt = r2(sum(x["target_eur"] for x in t if x["month_start"] <= latest))
    won = sum(1 for r in p if r["stage"] == "Won"); lost = sum(1 for r in p if r["stage"] == "Lost")
    return {"latest_month": latest,
            "revenue_eur": rev, "target_eur": tgt, "attainment": rev / tgt,
            "open_pipeline_eur": r2(sum(r["amount_eur"] for r in p if r["stage"] in OPEN_STAGES)),
            "weighted_pipeline_eur": r2(sum(r["weighted_eur"] for r in p if r["stage"] in OPEN_STAGES)),
            "win_rate": won / (won + lost)}


def top_customers(out, n=10):
    tot = {}
    for r in out["sales"]:
        if r["customer_id"]: tot[r["customer_name"]] = tot.get(r["customer_name"], 0.0) + r["amount_eur"]
    rows = sorted(((k, r2(v)) for k, v in tot.items()), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [{"rank": i + 1, "customer": k, "revenue_eur": v} for i, (k, v) in enumerate(rows)]


if __name__ == "__main__":
    o = run(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "base")
    print({k: len(v) for k, v in o.items()}); print(kpis(o))
    from collections import Counter; print(Counter(e["issue"] for e in o["exceptions"]))
