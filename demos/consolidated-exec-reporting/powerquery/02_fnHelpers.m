// Connection only. Name: fnHelpers. Shared rules, mirrored in scripts/pipeline.py.
[
    // Round half away from zero to cents (pipeline.r2)
    R2 = (x as nullable number) as nullable number =>
        if x = null then null else Number.Round(x, 2, RoundingMode.AwayFromZero),

    // Case-fold and keep letters/digits only (pipeline.norm_name)
    Norm = (v as any) as text =>
        Text.Combine(List.Select(Text.ToList(Text.Lower(Text.From(v ?? ""))),
            each Text.Lower(_) <> Text.Upper(_) or List.Contains({"0".."9"}, _))),

    // Numbers stay numbers. Text: drop spaces; if both "." and "," the LAST one is the decimal mark;
    // a lone comma + 1-2 digits is a decimal comma; "1,234" and "1.234" are ambiguous -> null (BAD_AMOUNT).
    Amount = (v as any) as nullable number =>
        if v is number then v
        else if v = null or v is logical then null
        else
            let
                digits = (x) => Text.Length(x) > 0 and Text.Select(x, {"0".."9"}) = x,
                t0 = Text.Remove(Text.From(v), {" ", Character.FromNumber(160)}),
                hasC = Text.Contains(t0, ","), hasD = Text.Contains(t0, "."),
                body = if Text.StartsWith(t0, "-") then Text.Middle(t0, 1) else t0,
                cParts = Text.Split(body, ","), dParts = Text.Split(body, "."),
                euThousands = hasD and not hasC and List.Count(dParts) >= 2
                    and Text.Length(dParts{0}) <= 3 and List.AllTrue(List.Transform(List.Skip(dParts, 1), each Text.Length(_) = 3 and digits(_))),
                t = if hasC and hasD then
                        (if Text.PositionOf(t0, ",", Occurrence.Last) > Text.PositionOf(t0, ".", Occurrence.Last)
                         then Text.Replace(Text.Replace(t0, ".", ""), ",", ".") else Text.Replace(t0, ",", ""))
                    else if hasC then
                        (if List.Count(cParts) = 2 and List.Contains({1, 2}, Text.Length(cParts{1})) then Text.Replace(t0, ",", ".") else "ambiguous")
                    else if euThousands then "ambiguous"
                    else t0,
                s = if Text.StartsWith(t, "-") then Text.Middle(t, 1) else t,
                parts = Text.Split(s, "."),
                ok = List.Count(parts) <= 2 and List.AllTrue(List.Transform(parts, digits))
            in
                if ok then Number.FromText(t, "en-US") else null,

    // Real dates, or text as dd.MM.yyyy / yyyy-MM-dd; anything else = null (BAD_DATE)
    Date = (v as any) as nullable date =>
        if v is date then v
        else if v is datetime then Date.From(v)
        else
            let t = Text.Trim(Text.From(v ?? "")) in
            try Date.FromText(t, [Format = "dd.MM.yyyy", Culture = "en-US"])
            otherwise try Date.FromText(t, [Format = "yyyy-MM-dd", Culture = "en-US"])
            otherwise null,

    IsBlankRow = (values as list) as logical =>
        List.MatchesAll(values, each _ = null or Text.Trim(Text.From(_)) = ""),

    // CSV with the delimiter detected from the header line (PL/DE Excel locales export with ";")
    Csv = (path as text) as table =>
        let
            bin = File.Contents(path),
            first = List.First(Lines.FromBinary(bin, null, null, 65001), ""),
            delim = if Text.Length(Text.Select(first, ";")) > Text.Length(Text.Select(first, ",")) then ";" else ","
        in
            Csv.Document(bin, [Delimiter = delim, Encoding = 65001, QuoteStyle = QuoteStyle.Csv])
]
