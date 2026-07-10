# My RAG Scoring Methodology — Project Health Reporting Agent

## My Approach to Health Scoring
When designing this project health reporting system, I decided to score project health across **five independent dimensions** rather than blending them into a single, generic average. My reasoning is that averaging metrics can dilute critical failures: a project with severe blockers and a slipped schedule shouldn't look "average Green" just because its budget is stable.

To prevent this, my scoring engine enforces a **"worst-of-five" overall RAG rule**. If even one dimension is flagged Red, the entire project is assessed as Red overall. This forces project managers and executives to see exactly which operational dimension is driving the risk, providing a direct diagnostic tool instead of just a high-level color flag.

---

## How I Map Signals to RAG Statuses
Here are the specific thresholds I implemented in my Signal Engine to convert spreadsheet metadata into RAG ratings:

| Dimension | Scoring Metric | Green (Low Risk) | Amber (Medium Risk) | Red (High Risk) |
|---|---|---|---|---|
| **Schedule Slippage** | Baseline Finish vs. Actual Finish date variance, rolled up from task to phase level. | ≤ 0 days of slip. | 1 to 10 days of slip. | > 10 days of slip, **or** if any task on the critical path is delayed. |
| **Milestone Health** | Percentage complete relative to elapsed time (today's date vs. planned start/finish). | On schedule or ahead of pace. | Up to 15% behind schedule pace. | More than 15% behind schedule pace. |
| **Blockers** | Share of tasks marked 'On Hold', 'Blocker', or flagged Red, weighted toward critical path. | < 5% of tasks are blocked. | 5% to 15% of tasks are blocked. | > 15% blocked, **or** if any critical-path task is put on hold. |
| **Budget Burn** | Cumulative actual cost compared to the baseline budget allocation. | Within budget limits. | Up to 10% over budget. | More than 10% over budget. *(If no cost columns exist, I mark this "Not Assessed")* |
| **Stakeholder Sentiment** | Keyword/phrase density scan of task comments (e.g., repeated "awaiting sign-off", escalation terms). | No unresolved requests or warnings. | 1 to 2 open requests older than a week. | 3 or more stale requests, or explicit escalation language. |

---

## How I Handle Messy and Incomplete Data
Real-world project spreadsheets are notoriously inconsistent. I built the following defensive principles into my Ingestion and Ingestion validation layers:

*   **Explicit Data Gaps ("Not Assessed"):** If a project spreadsheet is missing critical data columns (such as the complete absence of cost/budget columns in both Zycus sample files), my engine does not guess or default to Green. Instead, I explicitly mark the dimension as **"Not Assessed"** and record it in the weekly report's `data_gaps` list.
*   **Handling RAG Contradictions (Disagreement Flag):** Project managers often report their own subjective "Schedule Health" status. If my engine calculates an objective health score (e.g., Red due to a 15-day slip) that differs from the PM's self-reported status (e.g., Green), I raise a `disagreement_flag` to highlight this discrepancy for executive review.
*   **Defensive Parsing of Cells:** I parse date columns and status comments defensively. If a row contains unparseable or corrupted values, my ingestion engine logs a specific parsing error to the console and skips only that calculation rather than crashing the entire pipeline.

---

## Key Assumptions I Made
During implementation, I established the following logical assumptions:
1. **Critical Path Inference:** If the project spreadsheet does not contain an explicit critical-path column, I infer the critical path by identifying tasks that are marked as milestones or have dependency links directly impacting phase finish dates.
2. **Sentiment Source:** I restrict my sentiment analysis to the text comments already recorded inside the spreadsheet's task lists and comment tabs. I do not call external survey engines, keeping the analysis 100% self-contained.
3. **Point-in-Time Evaluation:** RAG scores are calculated fresh for the specific date input. They reflect the mathematical state of the project files on that day, rather than representing a moving average, so sudden changes are immediately visible.