// Name: Targets. LOAD to sheet Data_Targets, cell A1. Valid rows only; bad rows are on Exceptions as BAD_TARGET.
let
    S = Table.SelectRows(qTargetsStage, each [issue] = null),
    Sel = Table.SelectColumns(S, {"m", "r", "t"}),
    Ren = Table.RenameColumns(Sel, {{"m", "month_start"}, {"r", "region"}, {"t", "target_eur"}})
in
    Table.TransformColumnTypes(Ren, {{"month_start", type date}, {"region", type text}, {"target_eur", type number}})
