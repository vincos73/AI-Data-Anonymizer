# Contributing

Contributions are welcome, especially for Italian anonymization rules and false-positive reductions.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[build,web]"
python -m unittest discover -s tests -v
```

## Rule quality

AI Data Anonymizer favors precision over coverage. A new recognizer should include:

- at least one positive test;
- at least one false-positive test for common Italian text;
- no dependency on external services;
- no test fixtures containing real personal data.

## Pull requests

Keep changes small and explain the privacy tradeoff. If a rule may create false positives, document why it is still safe enough or make it opt-in.
