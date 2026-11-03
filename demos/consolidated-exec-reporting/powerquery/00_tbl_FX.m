// Connection only. Name: tbl_FX. Reads the Excel table tbl_FX on the Parameters sheet.
let
    Src = Excel.CurrentWorkbook(){[Name = "tbl_FX"]}[Content],
    Typed = Table.TransformColumnTypes(Src, {{"currency", type text}, {"rate_to_eur", type number}}),
    Trimmed = Table.TransformColumns(Typed, List.Transform({"currency"}, (c) => {c, Text.Trim, type text}))
in
    Trimmed
