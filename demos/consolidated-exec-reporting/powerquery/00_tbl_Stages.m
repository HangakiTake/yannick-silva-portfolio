// Connection only. Name: tbl_Stages. Reads the Excel table tbl_Stages on the Parameters sheet.
let
    Src = Excel.CurrentWorkbook(){[Name = "tbl_Stages"]}[Content],
    Typed = Table.TransformColumnTypes(Src, {{"stage", type text}, {"probability", type number}}),
    Trimmed = Table.TransformColumns(Typed, List.Transform({"stage"}, (c) => {c, Text.Trim, type text}))
in
    Trimmed
