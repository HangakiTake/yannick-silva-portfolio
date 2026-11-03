// Name: SchemaCheck. LOAD to sheet Checks, cell T4. One row per Excel source file.
let
    Files = (sub as text, layout as text) =>
        Table.AddColumn(Table.Sort(Table.SelectRows(Folder.Files(pInputFolder & sub & "\"),
            each Text.Lower([Extension]) = ".xlsx" and not Text.StartsWith([Name], "~$")), {"Name"}),
            "s", each let r = fnReadSalesFile([Content], [Name], layout) in r[Schema] & [rows_read = r[RowsRead]]),
    All = Table.Combine({Files("sales_pl", "PL"), Files("sales_dach", "DACH")})
in
    Table.FromRecords(All[s], {"file", "status", "missing_columns", "unmapped_columns", "rows_read"})
