// Connection only. Name: qSalesStage. Every sales row from both folders, parsed and checked, one issue per row.
let
    H = fnHelpers,
    Files = (sub as text, layout as text) =>
        let
            F = Table.SelectRows(Folder.Files(pInputFolder & sub & "\"),
                    each Text.Lower([Extension]) = ".xlsx" and not Text.StartsWith([Name], "~$")),
            S = Table.Sort(F, {"Name"}),
            R = Table.AddColumn(S, "r", each fnReadSalesFile([Content], [Name], layout))
        in Table.AddColumn(Table.SelectColumns(R, {"Name", "r"}), "layout", each layout),
    All = Table.Combine({Files("sales_pl", "PL"), Files("sales_dach", "DACH")}),
    FileIdx = Table.AddIndexColumn(All, "file_i", 0, 1),
    Ok = Table.SelectRows(FileIdx, each [r][Schema][status] = "OK"),
    Rows = Table.Combine(List.Transform(Table.ToRecords(Ok), (f) =>
        let t = f[r][Rows],
            t1 = if Table.HasColumns(t, "customer_id") then t else Table.AddColumn(t, "customer_id", each null)
        in Table.AddColumn(Table.AddColumn(t1, "source_file", each f[Name]), "file_i", each f[file_i]))),
    Sorted = Table.Sort(Rows, {{"file_i", Order.Ascending}, {"__row", Order.Ascending}}),
    Idx = Table.AddIndexColumn(Sorted, "__i", 0, 1),
    P = Table.AddColumn(Idx, "p", each
        let
            inv = Text.Trim(Text.From([invoice_no] ?? "")),
            d = H[Date]([invoice_date]),
            amt = H[Amount]([amount]),
            cur = Text.Upper(Text.Trim(Text.From([currency] ?? ""))),
            rate = List.First(Table.SelectRows(tbl_FX, (x) => x[currency] = cur)[rate_to_eur], null),
            ym = Text.Middle([source_file], Text.PositionOf([source_file], "20"), 7)
        in [inv = inv, d = d, amt = amt, cur = cur,
            eur = if amt <> null and rate <> null then H[R2](amt * rate) else null,
            ym = ym]),
    X = Table.ExpandRecordColumn(P, "p", {"inv", "d", "amt", "cur", "eur", "ym"}),
    FirstInv = Table.Group(X, {"inv"}, {{"first_i", each List.Min([__i])}}),
    J = Table.ExpandTableColumn(Table.NestedJoin(X, {"inv"}, FirstInv, {"inv"}, "fi", JoinKind.LeftOuter), "fi", {"first_i"}),
    Issue = Table.AddColumn(J, "issue", each
        if [inv] = "" then {"MISSING_INVOICE_NO", "Invoice number is blank"}
        else if [__i] > [first_i] then {"DUPLICATE_INVOICE", "Invoice number already loaded"}
        else if [d] = null then {"BAD_DATE", "Unreadable date '" & Text.From([invoice_date] ?? "") & "'"}
        else if [amt] = null then {"BAD_AMOUNT", "Amount is not a number '" & Text.From([amount] ?? "") & "'"}
        else if [eur] = null then {"BAD_CURRENCY", "Currency '" & [cur] & "' not in FX table"}
        else if Date.ToText([d], "yyyy-MM") <> [ym] then {"DATE_OUTSIDE_FILE_MONTH", "Date " & Date.ToText([d], "yyyy-MM-dd") & " is not in " & [ym]}
        else null),
    Acc = qAccounts,
    NameIdx = Table.Group(Acc, {"nkey"}, {{"ids", each [account_id]}}),
    Match = Table.AddColumn(Issue, "m", each
        let
            country = Text.Upper(Text.Trim(Text.From([country] ?? ""))),
            cid = Text.Trim(Text.From([customer_id] ?? "")),
            byId = Table.SelectRows(Acc, (a) => a[account_id] = cid),
            cands = List.First(Table.SelectRows(NameIdx, (n) => n[nkey] = H[Norm]([customer_name]) & "|" & country)[ids], {}),
            acct = if cid <> "" and not Table.IsEmpty(byId) then byId{0}
                   else if List.Count(cands) = 1 then Table.SelectRows(Acc, (a) => a[account_id] = cands{0}){0}
                   else null,
            method = if cid <> "" and not Table.IsEmpty(byId) then "id"
                     else if List.Count(cands) = 1 then "name"
                     else if List.Count(cands) > 1 then "ambiguous" else "unmatched"
        in [country = country, method = method, n_cands = List.Count(cands),
            customer_id = if acct = null then "" else acct[account_id],
            customer_name = if acct = null then "(unmatched) " & Text.Trim(Text.From([customer_name] ?? "")) else acct[account_name]]),
    Out = Table.ExpandRecordColumn(Table.RemoveColumns(Match, {"country", "customer_id"}), "m",
            {"country", "method", "n_cands", "customer_id", "customer_name"}, {"country", "match_method", "n_cands", "customer_id", "customer_name_std"})
in
    Out
