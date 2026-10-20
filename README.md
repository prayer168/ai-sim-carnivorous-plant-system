# AI-SIM Carnivorous Plant Inquiry Lab

AI-SIM demonstrates an evidence-centered inquiry about carnivorous plants. The public showcase includes a system introduction, an interactive six-stage student flow, and a teacher review example.

## Public showcase

The browser experience uses fixed synthetic choices and in-memory state only. It sends no student work to the server and clears the experience when the page reloads. The Python API starts in read-only public mode by default; all API `POST` requests receive `403 showcase_read_only`.

## Run locally

Requires Python 3.11 or newer. From the repository root:

```powershell
python -m app.server
```

Open <http://127.0.0.1:8000>. The page is served from `web/index.html`.

## Local API development

To exercise the full SQLite API locally, set `AI_SIM_PUBLIC_SHOWCASE=0` before startup. This enables write endpoints and uses the fixed demo bearer tokens described in `docs/OPERATIONS.md`; keep this development mode off public networks.

```powershell
$env:AI_SIM_PUBLIC_SHOWCASE = "0"
python -m app.server
```

Run the API acceptance suite with:

```powershell
python -m unittest discover -s tests -v
```

The suite explicitly turns API writes on for its isolated test database and separately verifies the public read-only behavior.

## Container

Docker Compose starts with public read-only mode enabled:

```powershell
docker compose up --build
```

The container listens on port 8000. The compose file expects a local `.env` copied from `.env.example`.

## Evidence and safety

- The six stages are observation, AI question, synthetic readings, analysis, CER, and teacher review.
- Original observations and sensor readings are append-only in API development mode; CER evidence references source IDs.
- The showcase makes no external AI calls and presents Mock AI questions as prompts, not scientific findings.
- Shared environment or lighting conditions are not independent experimental replicates.
- Charts describe sample values and cannot establish causation by themselves.

See `docs/OPERATIONS.md`, `docs/RISKS.md`, `docs/DATA_DICTIONARY.md`, and `tests/acceptance_matrix.md` for the API and its limits.
