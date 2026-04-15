# AGENTS.md

## Project
webgrab - universal web page fetcher with cascading fallback

## Rules
- NEVER commit secrets, API keys, credentials, tokens, or passwords to this repo or any repo
- use .env for local secrets, never hardcode
- all code must pass ruff (lint + format) and ty (type check)
- test coverage must stay >= 90%
- pre-commit runs ruff + ty + unit tests
- pre-push runs unit tests with 90% coverage enforcement
