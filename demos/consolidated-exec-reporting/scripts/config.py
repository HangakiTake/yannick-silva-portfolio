"""Shared constants. The Power Query side reads the same values from the
Parameters sheet; tests/test_requirements.py checks the workbook's Parameters tables match these values."""
FX_TO_EUR = {"EUR": 1.0, "PLN": 0.2345, "CHF": 1.0650, "CZK": 0.0398}
STAGE_PROB = {"Lead": 0.10, "Qualified": 0.25, "Proposal": 0.50,
              "Negotiation": 0.75, "Won": 1.0, "Lost": 0.0}
OPEN_STAGES = ["Lead", "Qualified", "Proposal", "Negotiation"]
REGION = {"PL": "PL", "DE": "DACH", "AT": "DACH", "CH": "DACH", "CZ": "CEE"}

# Excel source layouts. Standard column -> accepted header spellings.
PL_ALIASES = {
    "invoice_no": ["Nr faktury", "Numer faktury", "Invoice No"],
    "invoice_date": ["Data sprzedazy", "Data sprzedaży", "Data"],
    "customer_name": ["Klient", "Kontrahent"],
    "country": ["Kraj"],
    "amount": ["Kwota netto", "Kwota netto (PLN)", "Netto"],
    "currency": ["Waluta"],
}
DACH_ALIASES = {
    "invoice_no": ["Invoice No", "Rechnungsnr", "Invoice"],
    "customer_id": ["Cust ID", "Kundennr", "Customer ID"],
    "customer_name": ["Customer", "Kunde"],
    "country": ["Country", "Land"],
    "invoice_date": ["Invoice Date", "Rechnungsdatum"],
    "amount": ["Net Amount", "Netto", "Amount (net)"],
    "currency": ["Currency", "Währung"],
}
CRM_ACCOUNT_COLS = ["account_id", "account_name", "country", "owner"]
CRM_DEAL_COLS = ["deal_id", "account_id", "stage", "amount", "currency",
                 "expected_close", "owner"]
TARGET_COLS = ["month", "region", "target_eur"]
