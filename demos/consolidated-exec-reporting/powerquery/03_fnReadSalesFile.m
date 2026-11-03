// Connection only. Name: fnReadSalesFile. Finds the header row (first 10 rows),
// maps headers through tbl_Aliases, and either returns the rows or a FAILED schema record.
(content as binary, fileName as text, layout as text) as record =>
let
    H = fnHelpers,
    Sheet = Table.SelectRows(Excel.Workbook(content, false, true), each [Kind] = "Sheet"){0}[Data],
    RawCols = Table.ColumnNames(Sheet),
    // shortcut: row numbers assume the sheet's used range starts at row 1 (true for both layouts)
    Raw = Table.AddIndexColumn(Sheet, "__row", 1, 1),
    NonBlank = Table.SelectRows(Raw, each not H[IsBlankRow](List.Transform(RawCols, (c) => Record.Field(_, c)))),
    Aliases = Table.SelectRows(tbl_Aliases, each [layout] = layout),
    StdCols = List.Distinct(Aliases[std_column]),
    Anchors = List.Transform(Table.SelectRows(Aliases, each [std_column] = "invoice_no")[header], Text.Lower),
    CellText = (r, c) => Text.Lower(Text.Trim(Text.From(Record.Field(r, c) ?? ""))),
    HdrPos = List.PositionOf(
        List.Transform(Table.ToRecords(Table.FirstN(Raw, 10)),
            (r) => List.AnyTrue(List.Transform(RawCols, (c) => List.Contains(Anchors, CellText(r, c))))),
        true),
    Headers = if HdrPos < 0 then {} else List.Transform(RawCols, (c) => Text.Trim(Text.From(Record.Field(Raw{HdrPos}, c) ?? ""))),
    LowerHeaders = List.Transform(Headers, Text.Lower),
    Pos = List.Transform(StdCols, (s) => List.PositionOfAny(LowerHeaders,
            List.Transform(Table.SelectRows(Aliases, each [std_column] = s)[header], Text.Lower))),
    Optional = {"customer_id"},
    Missing = if HdrPos < 0 then {"header row not found in first 10 rows"}
              else List.Select(StdCols, (s) => Pos{List.PositionOf(StdCols, s)} < 0 and not List.Contains(Optional, s)),
    Found = List.Select(List.Positions(StdCols), (i) => Pos{i} >= 0),
    Unmapped = List.Select(List.Positions(Headers), (j) => Headers{j} <> "" and not List.Contains(Pos, j)),
    Schema = [file = fileName,
              status = if List.IsEmpty(Missing) then "OK" else "FAILED",
              missing_columns = Text.Combine(Missing, ", "),
              unmapped_columns = Text.Combine(List.Transform(Unmapped, each Headers{_}), ", ")],
    Body = Table.SelectRows(NonBlank, each [__row] > HdrPos + 1),
    Renamed = Table.RenameColumns(Body, List.Transform(Found, (i) => {RawCols{Pos{i}}, StdCols{i}})),
    Rows = Table.SelectColumns(Renamed, List.Transform(Found, (i) => StdCols{i}) & {"__row"})
in
    if Schema[status] = "OK"
    then [Schema = Schema, Rows = Rows, RowsRead = Table.RowCount(Body)]
    else [Schema = Schema, Rows = null, RowsRead = Table.RowCount(NonBlank)]
