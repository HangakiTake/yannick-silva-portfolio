# Stress test (run 2026-10-28T13:41Z, day 2026-11-02, mock data)

| Messy input | Result |
|---|---|
| UK-format date in register (01/04/2027) | PASS |
| Blank service date | PASS |
| Duplicate row, one written without the space (ZA04ECK) | PASS |
| Lower-case, extra spaces in register (" za15  pbk") | PASS |
| Missing document row typed lower-case without space (za03dvk) | PASS |
| Vehicle with no document rows at all (ZA16) | PASS |
| Envelope ID not in DocuSign | PASS |
| UTF-8 BOM + CRLF line endings (Excel export) | PASS |
| Blank registration row | PASS |
| "present" typed as Y / TRUE | PASS |
| Formula in a register cell (=HYPERLINK...) | PASS |
