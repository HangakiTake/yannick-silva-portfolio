"""Static checks on the M files (Power Query itself can't run on Linux)."""
import re
from pathlib import Path
PQ = Path(__file__).resolve().parents[1] / "powerquery"
FILES = sorted(PQ.glob("*.m"))
NAMES = {re.search(r"Name: (\w+)", f.read_text()).group(1): f for f in FILES}

def test_every_file_names_its_query():
    assert len(NAMES) == len(FILES)

def test_referenced_queries_exist_and_come_earlier():
    order = [n for n in NAMES]
    for i, (name, f) in enumerate(NAMES.items()):
        body = "\n".join(l for l in f.read_text().splitlines() if not l.strip().startswith("//"))
        body = re.sub(r'"[^"]*"', '""', body)  # ignore string literals
        for other in order:
            if other != name and re.search(rf"(?<![\w#\[]){other}(?![\w\]])", body):
                assert order.index(other) < i, f"{name} uses {other}, which is created later"

def test_brackets_balance():
    for f in FILES:
        t = re.sub(r'"[^"]*"', '""', "\n".join(l.split("//")[0] if not l.strip().startswith("//") else "" for l in f.read_text().splitlines()))
        for a, b in ("()", "[]", "{}"):
            assert t.count(a) == t.count(b), f"{f.name}: {a}{b} unbalanced"
