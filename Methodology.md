# My RAG Scoring Methodology: Project Health Reporting Agent

## My Approach to Health Scoring
I chose to score project health across five separate dimensions instead of combining them into one average. Averaging scores is a bad idea because it hides critical failures. If a project has massive blockers and a stalled schedule, it shouldn't show up as "mostly Green" just because it hasn't spent its budget yet.

To avoid this, my engine uses a strict "worst-of-five" rule. If even one score is Red, the whole project goes Red. This forces you to see exactly where the fire is.

---

## How I Map Signals to RAG Statuses
Here are the rules I wrote into the signal engine to turn raw spreadsheet data into RAG colors:

| Dimension | Scoring Metric | Green (Low Risk) | Amber (Medium Risk) | Red (High Risk) |
|---|---|---|---|---|
| **Schedule Slippage** | Baseline Finish vs. Actual Finish date variance. | 0 or fewer days of slip. | 1 to 10 days of slip. | More than 10 days of slip, or any delayed task on the critical path. |
| **Milestone Health** | Percentage complete relative to elapsed time (today's date vs. planned start/finish). | On schedule or ahead of pace. | Up to 15% behind schedule pace. | More than 15% behind schedule pace. |
| **Blockers** | Share of tasks marked "On Hold", "Blocker", or flagged Red, weighted toward the critical path. | Fewer than 5% of tasks are blocked. | 5% to 15% of tasks are blocked. | More than 15% blocked, or any critical-path task placed on hold. |
| **Budget Burn** | Cumulative actual cost compared to the baseline budget allocation. | Within budget limits. | Up to 10% over budget. | More than 10% over budget. (If there are no cost columns, I mark this "Not Assessed" rather than guessing a number). |
| **Stakeholder Sentiment** | Keyword scans of comments and notes for action items and escalations. | No unresolved requests or warnings. | 1 to 2 open requests older than a week (stale). | 3 or more stale requests, or explicit escalation keywords like "urgent" or "block" in comments. |

---

## How I Handle Messy and Incomplete Data
Spreadsheets are usually a mess. I wrote the code defensively to handle three specific issues:

*   **Missing columns ("Not Assessed"):** If a spreadsheet doesn't have a column (like the missing budget/cost columns in the sample files), I don't default to Green or 0. I mark that score "Not Assessed" and list it as a data gap in the report.
*   **Disagreement Flagging:** If the project manager writes "Green" on their status but the math shows a 15-day slip (Red), my engine raises a disagreement flag. The dashboard shows both ratings side-by-side so you can see if a PM is sugar-coating the status.
*   **Unparseable Dates and Cells:** If a cell has corrupted values or "#UNPARSEABLE" strings, the engine logs the error to the report's `data_gaps` and skips it, rather than crashing the pipeline.

---

## Key Assumptions I Made
I made a few assumptions while building this:
1. **Finding the Critical Path:** If the sheet doesn't tell me which tasks are on the critical path, I assume any task marked as a milestone or flagged as critical counts.
2. **Sentiment Source:** I only read the comments and notes directly inside the spreadsheet. I don't pull from Slack or email.
3. **Real-time calculations:** The scores represent the exact state of the file on the day you run the tool. I don't use moving averages.