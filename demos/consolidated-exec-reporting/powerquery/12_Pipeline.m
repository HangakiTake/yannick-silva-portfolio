// Name: Pipeline. LOAD to sheet Data_Pipeline, cell A1.
let
    S = Table.SelectRows(qDealsStage, each [issue] = null),
    A = Table.AddColumn(S, "account_name2", each if [known_account] then [account_name] else "(unknown account)"),
    C = Table.AddColumn(A, "country2", each if [known_account] then [country] else ""),
    R = Table.AddColumn(C, "region", each List.First(Table.SelectRows(tbl_Region, (x) => x[country] = [country2])[region], "Unknown")),
    W = Table.AddColumn(R, "weighted_eur", each fnHelpers[R2]([eur] * [prob]), type number),
    D = Table.AddColumn(W, "close", each fnHelpers[Date]([expected_close]), type date),
    Sel = Table.SelectColumns(D, {"deal_id", "account_id", "account_name2", "country2", "region", "stage2", "amt", "cur",
                                  "eur", "prob", "weighted_eur", "close", "owner"}),
    Ren = Table.RenameColumns(Sel, {{"account_name2", "account_name"}, {"country2", "country"}, {"stage2", "stage"},
            {"amt", "amount"}, {"cur", "currency"}, {"eur", "amount_eur"}, {"prob", "probability"}, {"close", "expected_close"}})
in
    Table.TransformColumnTypes(Ren, {{"amount", type number}, {"amount_eur", type number}, {"probability", type number}})
