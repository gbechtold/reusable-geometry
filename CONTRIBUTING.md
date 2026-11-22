# Contributing

Issues and pull requests are welcome.

## Ground rules

1. **A finding needs a measurement.** If you work around a kernel bug, record
   what you measured in `docs/WHY.md` - the operation, the inputs, the numbers
   it returned. "It did not work" is not reproducible; "cut returned 3920 mm³
   at tol 1e-4 and 2689 mm³ at 1e-3" is.
2. **A lesson becomes a test.** Anything that bit you once goes in `tests/`,
   so it cannot come back quietly.
3. **Fail loudly.** This package exists because OpenCascade returns empty
   faces and negative volumes without raising. New code should raise
   `GeometryError` with a message that names the likely cause, not return
   something plausible-looking.
4. **No dimension inside geometry code.** Numbers belong in a `ParamSet`,
   with their provenance.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
python examples/eyewear/front.py
python examples/eyewear/roundtrip.py
```

Both examples exit non-zero when a check fails, so they work in CI as they
stand.
