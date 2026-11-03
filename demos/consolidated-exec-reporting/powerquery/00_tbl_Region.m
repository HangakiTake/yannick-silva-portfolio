// Connection only. Name: tbl_Region. Reads the Excel table tbl_Region on the Parameters sheet.
let
    Src = Excel.CurrentWorkbook(){[Name = "tbl_Region"]}[Content],
    Typed = Table.TransformColumnTypes(Src, {{"country", type text}, {"region", type text}}),
    Trimmed = Table.TransformColumns(Typed, List.Transform({"country", "region"}, (c) => {c, Text.Trim, type text}))
in
    Trimmed
