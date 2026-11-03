// Name: Exceptions. LOAD to sheet Exceptions, cell A4.
let
    Cols = {"source_file", "source_row", "record_key", "issue", "detail", "amount_raw", "action"},
    AccDup = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qAccounts, each [is_duplicate])), (r) =>
        [source_file = "crm_accounts.csv", source_row = r[source_row], record_key = r[account_id], issue = "DUPLICATE_ACCOUNT",
         detail = "Same name and country as " & r[first_id], amount_raw = "", action = "Listed; merge in CRM"]), Cols),
    Rejected = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(SchemaCheck, each [status] <> "OK")), (r) =>
        [source_file = r[file], source_row = null, record_key = r[file], issue = "FILE_REJECTED",
         detail = "Missing required column(s): " & r[missing_columns], amount_raw = "", action = "Whole file skipped; fix header and refresh"]), Cols),
    SalesBad = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qSalesStage, each [issue] <> null)), (r) =>
        [source_file = r[source_file], source_row = r[__row], record_key = r[inv], issue = r[issue]{0}, detail = r[issue]{1},
         amount_raw = Text.From(r[amount] ?? ""), action = "Excluded from figures"]), Cols),
    Unmatched = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qSalesStage,
        each [issue] = null and ([match_method] = "unmatched" or [match_method] = "ambiguous"))), (r) =>
        [source_file = r[source_file], source_row = r[__row], record_key = r[inv],
         issue = if r[match_method] = "ambiguous" then "AMBIGUOUS_CUSTOMER" else "UNMATCHED_CUSTOMER",
         detail = if r[match_method] = "ambiguous" then "Name matches " & Text.From(r[n_cands]) & " CRM accounts"
                  else "'" & Text.Trim(Text.From(r[customer_name] ?? "")) & "' (" & r[country] & ") not found in CRM",
         amount_raw = Text.From(r[amount] ?? ""), action = "Included in revenue as (unmatched); fix name or add Cust ID"]), Cols),
    DealsBad = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qDealsStage, each [issue] <> null)), (r) =>
        [source_file = "crm_deals.csv", source_row = r[source_row], record_key = r[deal_id], issue = r[issue]{0}, detail = r[issue]{1},
         amount_raw = r[amount], action = "Excluded from figures"]), Cols),
    Unknown = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qDealsStage, each [issue] = null and not [known_account])), (r) =>
        [source_file = "crm_deals.csv", source_row = r[source_row], record_key = r[deal_id], issue = "UNKNOWN_ACCOUNT",
         detail = "Account '" & r[account_id] & "' not in CRM accounts", amount_raw = r[amount],
         action = "Included in pipeline as (unknown account); fix in CRM"]), Cols),
    NoRegion = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(Sales, each [region] = "Other")), (r) =>
        [source_file = r[source_file], source_row = r[source_row], record_key = r[invoice_no], issue = "UNKNOWN_COUNTRY",
         detail = "Country '" & r[country] & "' not in tbl_Region", amount_raw = Text.From(r[amount]),
         action = "Included in revenue under region Other; add the country to tbl_Region"]), Cols),
    TargetsBad = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(qTargetsStage, each [issue] <> null)), (r) =>
        [source_file = "targets.csv", source_row = r[source_row], record_key = Text.From(r[month] ?? ""), issue = r[issue]{0},
         detail = r[issue]{1}, amount_raw = Text.From(r[target_eur] ?? ""), action = "Excluded from targets"]), Cols)
in
    Table.Combine({AccDup, Rejected, SalesBad, Unmatched, NoRegion, DealsBad, Unknown, TargetsBad})
