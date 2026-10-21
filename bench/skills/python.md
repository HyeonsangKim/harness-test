# run_python (data pasted in the prompt)
1. Copy the pasted data into the program unchanged, as a triple-quoted string (DATA = """..."""). Do not retype or summarize it.
2. Parse it in code: csv.reader / csv.DictReader over io.StringIO(DATA) for tables (set delimiter for tab or |), str.splitlines() for lines. Strip spaces and remove commas and 원 before int().
3. Print checks first: number of rows parsed and the first row, so you can see the parsing is right. If the count does not match the data, fix the parser.
4. Compute everything in code: filters, sums, counts, sorting, date ranges. Never do arithmetic in your head. Money: int 원 or decimal.Decimal, not float. Dates: datetime.date / datetime.strptime; spell out whether range ends are included.
5. Print each final value with a label. Each call starts fresh, so every program must contain the data and all steps.
6. Standard library only (csv, io, json, re, datetime, decimal, collections, math). No pandas or numpy. If exit_code is not 0, read stderr, fix, run again.
7. Final reply: take values from the printed output and reply in exactly the requested format and nothing else. For JSON: one line, no ``` fences, no sentence before or after.
