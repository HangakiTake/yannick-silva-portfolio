// Name: Recon. LOAD to sheet Checks, cell A4. rows_read = rows_loaded + rows_excluded, and the same for EUR.
let
    R2 = fnHelpers[R2],
    S = qSalesStage,
    PerFile = Table.Group(S, {"source_file"}, {
        {"rows_read", each Table.RowCount(_), Int64.Type},
        {"rows_loaded", each Table.RowCount(Table.SelectRows(_, each [issue] = null)), Int64.Type},
        {"rows_excluded", each Table.RowCount(Table.SelectRows(_, each [issue] <> null)), Int64.Type},
        {"eur_source", each R2(List.Sum(List.RemoveNulls([eur])) ?? 0), type number},
        {"eur_loaded", each R2(List.Sum(Table.SelectRows(_, each [issue] = null)[eur]) ?? 0), type number},
        {"eur_excluded", each R2(List.Sum(List.RemoveNulls(Table.SelectRows(_, each [issue] <> null)[eur])) ?? 0), type number}}),
    WithSrc = Table.AddColumn(PerFile, "source", each if Text.StartsWith([source_file], "sales_pl") then "Excel PL" else "Excel DACH"),
    Rejected = Table.FromRecords(List.Transform(Table.ToRecords(Table.SelectRows(SchemaCheck, each [status] <> "OK")), (r) =>
        [source_file = r[file], source = "REJECTED", rows_read = r[rows_read], rows_loaded = 0, rows_excluded = 0,
         eur_source = null, eur_loaded = 0, eur_excluded = 0])),
    D = qDealsStage,
    Deals = #table({"source_file", "source", "rows_read", "rows_loaded", "rows_excluded", "eur_source", "eur_loaded", "eur_excluded"},
        {{"crm_deals.csv", "CRM", Table.RowCount(D), Table.RowCount(Table.SelectRows(D, each [issue] = null)),
          Table.RowCount(Table.SelectRows(D, each [issue] <> null)), R2(List.Sum(List.RemoveNulls(D[eur])) ?? 0),
          R2(List.Sum(Table.SelectRows(D, each [issue] = null)[eur]) ?? 0),
          R2(List.Sum(List.RemoveNulls(Table.SelectRows(D, each [issue] <> null)[eur])) ?? 0)}}),
    T = qTargetsStage, TOk = Table.SelectRows(T, each [issue] = null), TBad = Table.SelectRows(T, each [issue] <> null),
    Tg = #table(Table.ColumnNames(Deals), {{"targets.csv", "CSV", Table.RowCount(T), Table.RowCount(TOk), Table.RowCount(TBad),
          R2(List.Sum(List.RemoveNulls(T[t])) ?? 0), R2(List.Sum(TOk[t]) ?? 0), R2(List.Sum(List.RemoveNulls(TBad[t])) ?? 0)}}),
    A = Table.RowCount(qAccounts),
    Acc = #table(Table.ColumnNames(Deals), {{"crm_accounts.csv", "CRM", A, A, 0, 0, 0, 0}}),
    All = Table.Combine({Acc, Table.SelectColumns(WithSrc, Table.ColumnNames(Deals)), Rejected, Deals, Tg}),
    RowDiff = Table.AddColumn(All, "row_diff", each if [rows_read] = null then null else [rows_read] - [rows_loaded] - [rows_excluded], Int64.Type),
    EurDiff = Table.AddColumn(RowDiff, "eur_diff", each if [eur_source] = null then null else R2([eur_source] - [eur_loaded] - [eur_excluded]), type number)
in
    EurDiff
