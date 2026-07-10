# Project Health Reporting Agent

I built this tool to automate the tedious parts of project reporting: reading messy spreadsheets, working out objective RAG (Red/Amber/Green) health scores, generating brief plain-English narratives with the NVIDIA NIM API, and outputting everything into a clean PowerPoint presentation for stakeholders.

## Screenshots

The dashboard shows the calculated health scores next to what the project manager reported. In both sample projects, you can see the calculated health disagreeing with the PM's subjective status.

![Dashboard overview showing computed vs source-reported RAG status for two projects](assets/dashboard-overview.png)

The progress log tab shows the pipeline running live. Instead of a generic loading spinner, it streams terminal output as each ingestion, scoring, and reasoning stage completes.

![Pipeline progress panel showing ingestion and signal engine stages completing](assets/pipeline-progress.png)

The slide viewer renders a preview of the generated presentation directly in the web app.

![Exec deck viewer showing a cross-project trends slide](assets/exec-deck-viewer.png)

### CLI output

Running `python run.py weekly --all` processes both spreadsheet files. You can see the Reasoning Agent call to the NIM API and the resulting JSON report for project Titan, including the evidence strings backing up the Red rating.

![Terminal output of a weekly run against S2P Project.xlsx](assets/terminal-weekly-run.png)

`python run.py simulate` fakes history by running the pipeline across previous weeks, which gives the Synthesis Agent enough data to find trends.

![Terminal output of the simulate command generating historical weekly runs](assets/terminal-simulate.png)

`python run.py deck` compiles everything into a finished PowerPoint file at `output/exec_deck.pptx`.

![Terminal output of the deck build command, including model fallback attempts](assets/terminal-deck-build.png)

And `python run.py schedule` starts the APScheduler background job to run the weekly pipeline automatically.

![Terminal output showing the scheduler starting and registering the weekly job](assets/terminal-schedule.png)

### Generated output

Here is the JSON report generated for Titan. The computed overall RAG is Red, contradicting the reported Green.

![Weekly JSON report for S2P Project showing sub-scores and evidence](assets/weekly-report-s2p.png)

This is the JSON report for UniSan. The computed overall RAG is Amber, contradicting the reported Red.

![Weekly JSON report for Project Plan showing sub-scores and evidence](assets/weekly-report-plan.png)

And the deck itself, opened in a PowerPoint preview.

![Generated exec_deck.pptx opened in the editor showing the title slide and slide thumbnails](assets/exec-deck-slides.png)

## How it's put together

I split the pipeline into five separate stages. The main idea was to keep the scoring logic 100% mathematical and deterministic, and use the LLM only to write explanations. The model never decides the color of a project: it only narrates what the numbers already proved.

```
xlsx file(s)
   │
   ▼
[1] Ingestion       (pandas/pydantic, no LLM)
   │  maps whatever sheet layout you load into a common format
   ▼
[2] Signal Engine    (rule-based, no LLM)
   │  computes 5 sub-RAGs and an overall RAG, flags PM disagreement
   ▼
[3] Reasoning Agent   (1 NIM call per project)
   │  explains the score, citing specific delayed tasks
   ▼
[4] Synthesis Agent   (1 NIM call across all projects)
   │  compares projects to pull out trends
   ▼
[5] Deck Builder      (python-pptx, no LLM)
      turns all findings into a .pptx file
```

### Why not just hand the sheet to an LLM

Because spreadsheet data is full of contradictions. For example, in the Titan sheet, the task rows say "Schedule Health: Green" but the summary tab says "At Risk: High". If you give that straight to an LLM, you are guessing how it will resolve the conflict. My script calculates the color mathematically first, and then the LLM explains the conflict.

## Stack

- Python 3.11+
- pandas and openpyxl to read spreadsheets
- Pydantic v2 to validate data shapes
- NVIDIA NIM (using the OpenAI client) for the text summaries
- python-pptx to generate slides
- APScheduler for the background scheduling
- Next.js and Tailwind CSS for the read-only dashboard

No paid keys, no database, and no cloud accounts needed beyond the free NIM tier.

## Running it

Set up a venv like normal:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run it against one file, or everything in `data/samples/`:

```bash
python run.py weekly --file "data/samples/S2P Project.xlsx"
python run.py weekly --all
```

You can override the effective date too. This lets you simulate different dates without waiting for a week to pass:

```bash
python run.py weekly --all --effective-date 2026-06-15
```

To see the trend synthesis, you need more than one week of history. I wrote a simulation script that walks the date forward to build up 4 weeks of reports:

```bash
python run.py simulate
```

Once you have weekly runs saved, build the deck:

```bash
python run.py deck
# writes to output/exec_deck.pptx
```

If you want the pipeline to run automatically every Monday, start the background scheduler:

```bash
python run.py schedule
```

Or you can use cron directly:

```bash
0 9 * * 1 cd /path/to/project && source venv/bin/activate && python run.py weekly --all
```

## NIM setup

1. Register for a free account at [build.nvidia.com](https://build.nvidia.com)
2. Generate an API key (it starts with `nvapi-`)
3. Set the environment variable: `export NVIDIA_API_KEY="nvapi-your-key-here"`

If you do not set the key, the pipeline will still run. It will fall back to a simple template-based text narrative instead of calling the LLM.

## Some decisions worth explaining

- **No orchestrator frameworks**: I did not use LangGraph or CrewAI. This is a simple linear pipeline, so a basic python script in `src/orchestrator.py` was easier to write and read.
- **No guessing**: If the spreadsheets are missing columns (like budget data), the code marks the dimension "Not Assessed" and lists it as a data gap in the output.
- **Schema mapping**: The two sample files don't share a schema. S2P Project and Project Plan B use completely different column names for the same things, so the ingestion layer maps both to a single internal schema.
- **Validation tests**: I hand-calculated the expected scores for key dates and saved them as fixtures in `tests/fixtures/`. The test script `tests/test_validation.py` checks our code against these to prevent accidental regressions.
