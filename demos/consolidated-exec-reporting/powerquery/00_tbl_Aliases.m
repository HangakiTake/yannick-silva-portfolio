// Connection only. Name: tbl_Aliases. Reads the Excel table tbl_Aliases on the Parameters sheet.
let
    Src = Excel.CurrentWorkbook(){[Name = "tbl_Aliases"]}[Content],
    Typed = Table.TransformColumnTypes(Src, {{"layout", type text}, {"std_column", type text}, {"header", type text}}),
    Trimmed = Table.TransformColumns(Typed, List.Transform({"layout", "std_column", "header"}, (c) => {c, Text.Trim, type text}))
in
    Trimmed
