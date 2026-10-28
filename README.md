# Field Service Copilot

A permission-aware question-answering copilot for Corvane field technicians. It answers from Corvane's
documents, cites the source behind every sentence, uses only the documents the asking technician may see,
says when no permitted document covers the question, and drafts work orders for a person to approve.

## Repository layout

```
data/                    inputs, exactly as provided
  corpus/                42 exported files (PDF, DOCX, HTML, EML, CSV, JSON)
  eval/eval_questions.json
  permissions.json       groups each document requires
  users.json             technicians and their groups
src/
  common/                config, OpenAI client, access keys, trace
  offline_pipeline/      ingest: access reconciliation, dedupe, per-document LLM parse, chunk, embed, index
  online_query/          query: retrieve (BM25 + vectors, filtered by access), claims, verify, compose,
                         work order draft, pipeline runner
  evaluation/            eval suite (in progress)
  cli.py                 the `copilot` command
test/                    unit tests, mirroring src/
artifacts/index.db       the built search index, so queries work without re-ingesting
config.yaml              paths, models, retrieval and ingest settings
pyproject.toml           package and dependencies
```

## Setup

### 1. Get the code
The repository is private. Log in to GitHub with an account that has been given access, then clone:
```bash
gh auth login                                   # GitHub CLI: choose GitHub.com, HTTPS, log in with a browser
gh repo clone nehaannajohn/field-service-copilot
cd field-service-copilot
```

### 2. Create the environment
Requires Python 3.12 and [uv](https://docs.astral.sh/uv/):
```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
```

### 3. Set the OpenAI API key
Create a `.env` file in the repository root (it is git-ignored):
```bash
echo 'OPENAI_API_KEY=sk-...' > .env
```
Or export it in the shell instead: `export OPENAI_API_KEY=sk-...`

### 4. Check
```bash
.venv/bin/pytest -q          # unit tests, no API calls
.venv/bin/copilot --help
```

## Usage

### Ask a question as a technician
User ids are in `data/users.json`.
```bash
.venv/bin/copilot ask --user u03 "TAC-C-0143 tripped on E-31. How do I reset it?"
.venv/bin/copilot ask --user u02 --trace "TAC-C-0143 tripped on E-31. How do I reset it?"
```
The answer shows a summary with source markers (✓ supported, ✗ contradicted), an evidence table, and,
when follow-up is needed, a work order draft followed by an approve prompt (y/n). Approved work orders are
written to `artifacts/outbox/`. `--trace` prints every pipeline stage with its inputs, outputs and time.

### Ingest
Paths are relative to `data/`.
```bash
.venv/bin/copilot ingest corpus/bulletins/Halden_SB-2025-009_HCP-350_Casing_Torque.pdf   # a sample
.venv/bin/copilot ingest                                                                  # full corpus (~20 min)
```
Ingest updates `artifacts/index.db` and writes `artifacts/ingest_report.json` with the status of every file.

## Where AI helped

I used Claude Code as my AI agent across design and implementation.

- **Design.** I started from a skeleton design and iterated with the agent, section by section, until we agreed
  on each part. The agent read the brief and the corpus and surfaced the data issues (missing permissions entry,
  corrupt and empty files, the scanned manual, duplicates, contradicting sources); I made the design decisions.
- **Implementation.** Step by step: the agent proposed each code snippet, I reviewed it and changed it where
  needed, and only then was it written. Every live model run was approved before it ran.
