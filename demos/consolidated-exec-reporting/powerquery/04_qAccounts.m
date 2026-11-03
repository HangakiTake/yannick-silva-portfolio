// Connection only. Name: qAccounts. CRM accounts with a duplicate flag (same normalised name + country).
let
    H = fnHelpers,
    Src = H[Csv](pInputFolder & "crm\crm_accounts.csv"),
    Promoted = Table.PromoteHeaders(Src, [PromoteAllScalars = true]),
    WithRow = Table.AddIndexColumn(Promoted, "source_row", 2, 1),
    NonBlank = Table.SelectRows(WithRow, each not H[IsBlankRow]({[account_id], [account_name], [country], [owner]})),
    Clean = Table.TransformColumns(NonBlank, {{"account_id", Text.Trim}, {"country", each Text.Upper(Text.Trim(_))}}),
    Keyed = Table.AddColumn(Clean, "nkey", each H[Norm]([account_name]) & "|" & [country], type text),
    Idx = Table.AddIndexColumn(Keyed, "__i", 0, 1),
    FirstOf = Table.Group(Idx, {"nkey"}, {{"first_i", each List.Min([__i])}, {"first_id", each Table.Sort(_, {"__i"}){0}[account_id]}}),
    Joined = Table.NestedJoin(Idx, {"nkey"}, FirstOf, {"nkey"}, "f", JoinKind.LeftOuter),
    Out = Table.ExpandTableColumn(Joined, "f", {"first_i", "first_id"}),
    Flag = Table.AddColumn(Out, "is_duplicate", each [__i] > [first_i], type logical)
in
    Table.Sort(Flag, {"__i"})
