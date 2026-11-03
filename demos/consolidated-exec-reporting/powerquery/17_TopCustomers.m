// Name: TopCustomers. LOAD to sheet Dashboard, cell N5 (Top 10 customers). Matched customers only.
let
    S = Table.SelectRows(Sales, each [customer_id] <> ""),
    G = Table.Group(S, {"customer_name"}, {{"revenue_eur", each fnHelpers[R2](List.Sum([amount_eur])), type number}}),
    Sorted = Table.Sort(G, {{"revenue_eur", Order.Descending}, {"customer_name", Order.Ascending}}),
    Top = Table.FirstN(Sorted, 10),
    Ranked = Table.AddIndexColumn(Top, "rank", 1, 1)
in
    Table.SelectColumns(Table.RenameColumns(Ranked, {{"customer_name", "customer"}}), {"rank", "customer", "revenue_eur"})
