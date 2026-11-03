// Connection only. Name: qDealsStage. CRM deals parsed and checked; Pipeline (12) loads from it.
let
    H = fnHelpers,
    Src = H[Csv](pInputFolder & "crm\crm_deals.csv"),
    Promoted = Table.PromoteHeaders(Src, [PromoteAllScalars = true]),
    WithRow = Table.AddIndexColumn(Promoted, "source_row", 2, 1),
    NonBlank = Table.SelectRows(WithRow, each not H[IsBlankRow]({[deal_id], [account_id], [stage], [amount], [currency]})),
    P = Table.AddColumn(NonBlank, "p", each
        let amt = H[Amount]([amount]), cur = Text.Upper(Text.Trim([currency])), stage = Text.Trim([stage]),
            rate = List.First(Table.SelectRows(tbl_FX, (x) => x[currency] = cur)[rate_to_eur], null),
            prob = List.First(Table.SelectRows(tbl_Stages, (x) => x[stage] = stage)[probability], null),
            eur = if amt <> null and rate <> null then H[R2](amt * rate) else null
        in [amt = amt, cur = cur, stage2 = stage, eur = eur, prob = prob,
            issue = if amt = null then {"BAD_AMOUNT", "Amount is not a number '" & [amount] & "'"}
                    else if eur = null then {"BAD_CURRENCY", "Currency '" & cur & "' not in FX table"}
                    else if prob = null then {"BAD_STAGE", "Unknown stage '" & stage & "'"} else null]),
    X = Table.ExpandRecordColumn(P, "p", {"amt", "cur", "stage2", "eur", "prob", "issue"}),
    Acc = Table.SelectColumns(qAccounts, {"account_id", "account_name", "country"}),
    J = Table.NestedJoin(Table.TransformColumns(X, {{"account_id", Text.Trim}}), {"account_id"}, Acc, {"account_id"}, "a", JoinKind.LeftOuter),
    E = Table.ExpandTableColumn(J, "a", {"account_name", "country"}),
    Known = Table.AddColumn(E, "known_account", each [account_name] <> null, type logical)
in
    Known
