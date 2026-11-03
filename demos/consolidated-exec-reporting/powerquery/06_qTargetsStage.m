// Connection only. Name: qTargetsStage. targets.csv parsed and checked; Targets (13) loads the valid rows.
let
    H = fnHelpers,
    Src = H[Csv](pInputFolder & "targets.csv"),
    P = Table.PromoteHeaders(Src, [PromoteAllScalars = true]),
    WithRow = Table.AddIndexColumn(P, "source_row", 2, 1),
    NonBlank = Table.SelectRows(WithRow, each not H[IsBlankRow]({[month], [region], [target_eur]})),
    T = Table.AddColumn(NonBlank, "p", each
        [m = H[Date]([month]), r = Text.Trim(Text.From([region] ?? "")), t = H[Amount]([target_eur])]),
    X = Table.ExpandRecordColumn(T, "p", {"m", "r", "t"}),
    Issue = Table.AddColumn(X, "issue", each
        if [m] = null or [t] = null or [r] = "" then
            {"BAD_TARGET", "Unreadable target row: month '" & Text.From([month] ?? "") & "', region '" & [r] & "', target '" & Text.From([target_eur] ?? "") & "'"}
        else null)
in
    Issue
