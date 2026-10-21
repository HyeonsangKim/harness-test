# ERP tools
1. Start with list_tables. Pick the table whose description matches what was asked (period, kind of data). Tables marked backup / 조회 전용 / old year are not current data unless the user asks for them.
2. Call describe_table before filtering, and use only the exact column names it returns. If the user names something by label (부서명, 거래처명), first look up its code in the master table, then filter by the code.
3. Turn every condition in the request into a filter: status, code, and both ends of a date range (dates are 'YYYY-MM-DD' text, so ">=" and "<=" work). "이상/이하" means >= / <=; "초과/미만" means > / <.
4. For counts, sums, averages, max/min, use aggregate with the same filters. Never add or count rows in your head.
5. When you need the rows themselves (a list of codes), use query and keep calling with offset = next_offset until next_offset is null. Check that the number of rows you collected equals `total`.
6. Use calculate only for arithmetic that combines numbers you already got from tools. Do not call it just to repeat a number.
7. Final reply: exactly the requested format and nothing else. For JSON: one line, no ``` fences, no sentence before or after, integers without commas or 원.
