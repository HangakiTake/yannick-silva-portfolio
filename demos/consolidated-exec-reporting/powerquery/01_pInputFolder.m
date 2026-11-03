// Connection only. Name: pInputFolder. Folder that holds crm\, sales_pl\, sales_dach\ and targets.csv.
// Read from the named cell InputFolder on the Parameters sheet; always ends with "\".
let
    Raw = Text.Trim(Text.From(Excel.CurrentWorkbook(){[Name="InputFolder"]}[Content]{0}[Column1])),
    Folder = if Text.EndsWith(Raw, "\") or Text.EndsWith(Raw, "/") then Raw else Raw & "\"
in
    Folder
