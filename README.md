# LedgerSim

LedgerSim is a deterministic domain kernel for simulating business records,
economic facts, reported accounting, normative accounting, and fraud labels.

The repository is currently implementing Phase 1A. This phase contains only
pure domain code and executable golden tests. PostgreSQL persistence, branching,
dataset export, frontends, and agent integration are explicitly deferred.

## Development

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen python fixtures/golden/validate_sales_fraud_v1.py
```

The script in `fixtures/golden/` is a static fixture linter. Domain truth is
executed by `src/ledger_sim/domain/` and checked against the frozen fixture by
the tests in `tests/golden/`.
