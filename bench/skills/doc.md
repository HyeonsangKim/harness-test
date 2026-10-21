# Document tools
1. Call list_documents and choose the document by title (company, kind of document, subject). If several could match, read each candidate's start before choosing.
2. read_document returns at most 3000 characters. Keep calling with offset = next_offset until next_offset is null, unless you have already found the exact sentence that answers the question.
3. Find the sentence that states the answer and use the value written there. Do not compute a value the document already states (예: 합계, 부가세 포함 금액). Compute only if the document does not state it, and then use a tool or check it carefully against the stated parts.
4. Watch for look-alike values: a total vs. a subtotal (공급가액), with vs. without VAT, contract period vs. notice period vs. cancellation notice. Match the exact wording of the question.
5. Convert to the requested form: dates "2025년 3월 5일" → "2025-03-05"; money "1,234,000원" → 1234000; "14일" → 14.
6. Final reply: exactly the requested format and nothing else. For JSON: one line, no ``` fences, no sentence before or after.
