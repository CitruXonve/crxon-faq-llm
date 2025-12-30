# RAG FAQ Backend

A straight-forward FastAPI backend of knowledge base, LLM and RAG for retrieval.

## Quick Start

### Prerequisite

- `Python >= 3.11`
- `Poetry >= 2.0`

### Dependency resolution

This is to set up a virtual environment in the project directory:

```bash
python -m venv .venv
```

Resolve dependencies via `poetry`:

```bash
poetry update
poetry install
```

Optional: in case of the error ` pyproject.toml changed significantly since poetry.lock was last generated. Run ``poetry lock`` to fix the lock file. `

```bash
poetry lock
```

### Run server locally

```bash
fastapi dev src/main.py
```

Once running, the server should listen to `127.0.0.1:8000` by default.

### Debug server locally

```bash
fastapi dev src/main.py --reload
```

### Run unit testing

```bash
python -m unittest tests/*.py
```

## TODOs

- MCP-based integration with OneNote etc.
- Streaming response via server-sent events (SSE)
- DB storage of sessions instead of in memory
- Fine-tuning on models, chunking and embedding
