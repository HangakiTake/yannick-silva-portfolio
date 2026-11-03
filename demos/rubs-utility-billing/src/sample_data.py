"""Synthetic sample data (fictional properties, units and bills)."""
from datetime import date

PROPERTIES = [("P1", "Maple Court (4 units)"), ("P2", "Harbor View (8 units)"), ("P3", "Cedar Lofts (12 units)")]

# unit_id, prop, sqft, discount, marked_vacant, excluded services
UNITS = []
for n in range(1, 5):
    UNITS.append([f"P1-{n:02d}", "P1", 650 + 50 * n, 0, "N", set()])
for n in range(1, 9):
    UNITS.append([f"P2-{n:02d}", "P2", 700 + 25 * n, 0, "N", set()])
for n in range(1, 13):
    UNITS.append([f"P3-{n:02d}", "P3", 500 + 40 * n, 0, "N", set()])
U = {u[0]: u for u in UNITS}
U["P1-03"][3] = 0.10            # 10% discount (e.g. on-site manager)
U["P2-04"][5] = {"Gas"}         # unit has electric heating, no gas
U["P3-07"][5] = {"Gas"}
U["P2-08"][4] = "Y"             # marked vacant (renovation)

OCT1, OCT31 = date(2026, 10, 1), date(2026, 10, 31)
OCCUPANCY = []                  # unit, occupants, move_in, move_out
occ_counts = {"P1-01": 2, "P1-02": 1, "P1-03": 3, "P1-04": 4,
              "P2-01": 2, "P2-02": 2, "P2-03": 1, "P2-04": 3, "P2-05": 2, "P2-06": 5, "P2-07": 1,
              "P3-01": 1, "P3-02": 2, "P3-03": 2, "P3-04": 3, "P3-05": 1, "P3-06": 2, "P3-07": 4,
              "P3-08": 2, "P3-09": 1, "P3-11": 2, "P3-12": 3}
for u, n in occ_counts.items():
    OCCUPANCY.append([u, n, None, None])
# P2-08 vacant (renovation). P3-10 vacant until mid-month move-in.
OCCUPANCY.append(["P3-10", 2, date(2026, 10, 16), None])
# P2-05: tenant moved out 20 Oct, new household of 3 from 25 Oct.
for row in OCCUPANCY:
    if row[0] == "P2-05":
        row[3] = date(2026, 10, 20)
OCCUPANCY.append(["P2-05", 3, date(2026, 10, 25), None])
# P1-02 occupant count rose from 1 to 2 on 11 Oct.
for row in OCCUPANCY:
    if row[0] == "P1-02":
        row[3] = date(2026, 10, 10)
OCCUPANCY.append(["P1-02", 2, date(2026, 10, 11), None])

BILLS = [  # id, prop, service, start, end, amount
    ["B-101", "P1", "Water", date(2026, 9, 18), date(2026, 10, 17), 412.37],
    ["B-102", "P1", "Sewer", OCT1, OCT31, 288.90],
    ["B-103", "P1", "Trash", OCT1, OCT31, 145.00],
    ["B-104", "P1", "Gas", OCT1, OCT31, 203.11],
    ["B-201", "P2", "Water", OCT1, OCT31, 781.43],
    ["B-202", "P2", "Sewer", OCT1, OCT31, 655.02],
    ["B-203", "P2", "Trash", OCT1, OCT31, 260.00],
    ["B-204", "P2", "Gas", OCT1, OCT31, 498.77],
    ["B-301", "P3", "Water", OCT1, OCT31, 1190.58],
    ["B-302", "P3", "Sewer", OCT1, OCT31, 1004.16],
    ["B-303", "P3", "Trash", OCT1, OCT31, 390.00],
    ["B-304", "P3", "Gas", OCT1, OCT31, 845.39],
    ["B-305", "P3", "Other", OCT1, OCT31, 120.00],   # pest control
]

RULES = [  # prop, service, method, vacant_weight, owner_paid_pct
    ["P1", "Water", "Occupants", 0, 0], ["P1", "Sewer", "Occupants", 0, 0],
    ["P1", "Trash", "Equal", 0, 0.15], ["P1", "Gas", "Occupants", 0, 0],
    ["P2", "Water", "Occupants", 1, 0], ["P2", "Sewer", "Occupants", 1, 0],
    ["P2", "Trash", "Equal", 1, 0.15], ["P2", "Gas", "SqFt", 1, 0],
    ["P3", "Water", "Occupants", 0, 0], ["P3", "Sewer", "Occupants", 0, 0],
    ["P3", "Trash", "Equal", 0, 0.15], ["P3", "Gas", "SqFt", 0, 0],
    ["P3", "Other", "Equal", 1, 0],
]
