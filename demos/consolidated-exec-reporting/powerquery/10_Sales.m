// Name: Sales. LOAD to sheet Data_Sales, cell A1. Column order is fixed: dashboard formulas use column letters.
let
    S = Table.SelectRows(qSalesStage, each [issue] = null),
    A = Table.AddColumn(S, "month_start", each Date.StartOfMonth([d]), type date),
    R = Table.AddColumn(A, "region", each List.First(Table.SelectRows(tbl_Region, (x) => x[country] = [country])[region], "Other"), type text),
    Sel = Table.SelectColumns(R, {"inv", "source_file", "__row", "d", "month_start", "customer_id", "customer_name_std",
                                  "country", "region", "amt", "cur", "eur", "match_method"}),
    Ren = Table.RenameColumns(Sel, {{"inv", "invoice_no"}, {"__row", "source_row"}, {"d", "invoice_date"},
            {"customer_name_std", "customer_name"}, {"amt", "amount"}, {"cur", "currency"}, {"eur", "amount_eur"}})
in
    Table.TransformColumnTypes(Ren, {{"invoice_date", type date}, {"source_row", Int64.Type},
        {"amount", type number}, {"amount_eur", type number}})
