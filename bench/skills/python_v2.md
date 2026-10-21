# run_python (data pasted in the prompt)
1. The user's whole message is saved as input.txt in the working directory. Read it with text = open('input.txt', encoding='utf-8').read(). Never retype or copy the pasted data into your code.
2. Cut the part you need out of text (for a table: the lines from the header line to the last data row) and parse it in code: csv.reader / csv.DictReader over io.StringIO(...), str.splitlines() for lines. Strip spaces and remove commas and 원 before int().
3. Print a check first: number of rows parsed and the first row. If the count does not match the data, fix the parser.
4. Compute everything in code: filters, sums, counts, sorting, date ranges. Never do arithmetic in your head. Money: int 원 or decimal.Decimal, not float. Dates: datetime.date / datetime.strptime; follow the stated rules on included range ends and rounding.
5. When the answer format is JSON, make the LAST printed line the final answer in exactly that format, built with json.dumps(..., ensure_ascii=False). That line is used as your reply, so do it in the same program that computes the values.
6. Standard library only (csv, io, json, re, datetime, decimal, collections, math). No pandas or numpy. If exit_code is not 0, read stderr, fix, run again.
7. If you reply yourself, use exactly the requested format and nothing else (JSON: one line, no ``` fences, no sentence before or after; code: the requested code block).
