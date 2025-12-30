# RAG FAQ Backend

A straight-forward FastAPI backend of knowledge base, LLM and RAG for retrieval.

## Quick Start

### Prerequisites

This project depends on an API key in a Claude/Anthropic account to query the LLMs (see [Claude Console](https://console.anthropic.com/)).

Upon obtaining an [API key](https://console.anthropic.com/settings/keys), it can be secured locally in this way:

```bash
cat "CLAUDE_API_KEY=[YOUR_API_KEY]" >> .env
cat "CLAUDE_MODEL=claude-sonnet-4-5-20250929" >> .env   # default LLM model in this project
cat "CLAUDE_MAX_TOKENS=1024" >> .env                    # limit token consumption
source .env

# test API key access
echo $CLAUDE_API_KEY
```

Note that `.env` file already exists in `.gitignore` so as not to be committed into the code repo.

To avoid the inconvenience of loading the `.env` file every time of entering the project directory, it is recommended to install `direnv` if in macOS.

```bash
brew install direnv

# create a ".envrc" file under the project directory
direnv allow

# for zsh
echo '# direnv' >> ~/.zshrc
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
```

### Dependency resolution

Dependencies:

- `Python >= 3.11`
- `Poetry >= 2.0`

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
