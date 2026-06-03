# Subagent Prompt Template (Core Page Parity)

Use this template per subagent with only its assigned route group.

---
You are validating page-visible parity between legacy and python contours.

Scope:
- Compare only assigned URL pairs.
- Legacy base: `http://127.0.0.1:8181/hlstats.php`
- Python base: `http://127.0.0.1:8281/hlstats.php`

Rules:
- Read-only only. Do not trigger destructive actions.
- Verdict is based on visible page data.
- SQL is optional only to explain mismatch source.

For each assigned route:
1. Open legacy URL and python URL with identical query params.
2. Compare:
   - counters/totals
   - first visible rows and key values
   - sorting/filtering/pagination behavior
   - empty/non-empty state text
3. Emit one line per mismatch in JSON:
   - `route`
   - `legacy_url`
   - `python_url`
   - `severity` (`P0|P1|P2|P3`)
   - `difference` (short)
   - `repro` (short)

Output:
- Return only mismatches as JSONL-like lines.
- If no mismatch, return `NO_DIFF`.
---
