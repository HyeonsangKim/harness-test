# Code workspace tools
1. Read the file to change and its test file before editing. If the bug is unclear, run_tests first and read the failing assert.
2. Before editing, list every requirement in the user's request, including error cases (예: "ValueError를 내야 합니다"). Tests may check only some of them; your code must satisfy all of them.
3. Make the smallest change that fixes the cause. Keep existing functions, names and behavior that the request did not mention.
4. replace_in_file: `old` must be copied exactly from the file (spaces, quotes, newlines) and appear once. Use a short unique piece, such as one full line. If it fails, read_file again and copy the text from the fresh output.
5. To add a new function, replace a short unique anchor (the last line of the file) with that line plus the new code. Use write_file only for new files or a full rewrite.
6. Use only the standard library. Put imports at the top of the file.
7. After every edit, run_tests. If it fails, read the error, fix, and run again. Do not run tests twice without changing anything in between.
8. Finish only when exit_code is 0. Then reply in one or two lines: which file and function you changed and why.
