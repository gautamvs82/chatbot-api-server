# My Package

A standard Python project built using PyCharm.

## Getting Started

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install development dependencies:
   ```bash
   pip install -e .[dev]
   ```

3. Run tests:
   ```bash
   pytest
   ```
Run the HTTP server
uvicorn main:app --host 0.0.0.0 --port 5090