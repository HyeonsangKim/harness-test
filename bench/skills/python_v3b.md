# run_python (data pasted in the prompt)
1. Tables in the user's message are already saved as table_1.csv, table_2.csv, ... (listed in the tool description with their delimiter and columns). Read them with csv.DictReader(open('table_1.csv', encoding='utf-8'), delimiter=...). Never retype or copy the data into your code.
2. The whole message is also in input.txt (open('input.txt', encoding='utf-8').read()) for anything that is not a table. Strip spaces and remove commas and 원 before int().
3. Print a check first: number of rows parsed and the first row. If the count does not match the data, fix the parser.
4. Compute everything in code: filters, sums, counts, sorting, date ranges. Never do arithmetic in your head. Money: int 원 or decimal.Decimal, not float. Dates: datetime.date / datetime.strptime; follow the stated rules on included range ends and rounding.
5. Print each final value with a label. Then check the output against the rules in the request (rounding, included dates, exclusions) before you reply.
6. Standard library only (csv, io, json, re, datetime, decimal, collections, math). No pandas or numpy. If exit_code is not 0, read stderr, fix, run again.
7. If you reply yourself, use exactly the requested format and nothing else (JSON: one line, no ``` fences, no sentence before or after; code: the requested code block).
