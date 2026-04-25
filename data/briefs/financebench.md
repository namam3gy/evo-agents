# FinanceBench — domain brief for the architecture controller

## What the task family looks like
The worker receives a question about a specific U.S. publicly traded company and one or more excerpts pulled from that company's SEC filings (10-K, 10-Q, earnings releases, MD&A discussion). The expected answer is a short, fact-grounded answer string — sometimes a number with units, sometimes a one-sentence interpretation, sometimes a yes/no on a policy.

Examples of the question style:
- "What is the nature & purpose of AMCOR's restructuring liability as of Q2 of FY2023 close?"
- "What was Coca-Cola's FY2022 operating margin?"
- "Has Walmart paid a special dividend in the last 5 years?"

## Failure modes seen in real runs (be specific when proposing fixes)
- **Unit confusion** — millions vs thousands, $K vs $M, basis points vs percent. The evidence often interleaves units inside a single table row.
- **Period confusion** — fiscal year vs calendar year (e.g., NVIDIA FY2024 = calendar 2023), trailing twelve months vs annual, "as of" balance-sheet vs "for the period" income-statement.
- **GAAP vs non-GAAP** — confusing reported net income with adjusted EBITDA, or operating income with segment income. Companies report multiple metrics with similar names.
- **Tabular parsing** — the right column or footnote is missed; numbers in the wrong column are pulled.
- **Forward-looking vs historical** — guidance language ("expected", "we anticipate") is conflated with realized actuals.
- **Multi-step calculation** — the answer requires combining 2+ line items (e.g., free cash flow = operating CF − capex).
- **Footnote / disclosure literacy** — important caveats live in footnotes, not in the headline number.

## Useful expertise (cite when authoring agent personas)
- **GAAP-trained financial analyst** focused on income statement, balance sheet, cash-flow-statement interpretation.
- **10-K MD&A specialist** — narrative analysis, segment reporting, risk-factor parsing.
- **Industry KPI specialist** — knows what metric matters per industry (gross margin for retail, ARR/NRR for SaaS, AUM for asset managers, loan-loss provisions for banks).
- **Footnote / disclosure auditor** — reads the small print that adjusts the headline number.
- **Numerical extractor** — disciplined at "evidence → number with units" with no interpretation.

## Reasoning patterns that work
1. Identify the **time period** and **reporting standard** the question implies, before reading the evidence.
2. Locate the relevant statement / table / paragraph in the evidence and extract the number with units.
3. If multiple periods are present, check which one matches the question.
4. If the question asks about composition / share / ratio, do the arithmetic explicitly.
5. Cross-check against any related fields if available (e.g., consistency between cash-flow and balance-sheet movement).
6. State the final answer concisely with units and period.

## Anti-patterns the controller should avoid
- A generic "verifier" that re-reads the executor's output without any finance-specific check (units, period, statement type) is approximately useless here.
- A "summarizer" that compresses a numeric answer into prose loses information.
- Adding more agents that all do the same parsing work in parallel does not help — they share the same failure mode.
