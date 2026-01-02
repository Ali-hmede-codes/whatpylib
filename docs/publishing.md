# Publishing to PyPI

This guide explains how to publish `WhatPyLib` to the Python Package Index (PyPI) so others can install it via `pip install whatpylib`.

## Prerequisites

1.  **PyPI Account**: Create an account at [pypi.org](https://pypi.org/).
2.  **API Token**: Go to Account Settings > API Tokens and create a new token. Save it securely.

## Step 1: Install Build Tools

You need `build` to create the package and `twine` to upload it.

```bash
pip install build twine
```

## Step 2: Build the Package

Run this command in the root directory (where `pyproject.toml` is):

```bash
python -m build
```

This will create a `dist/` directory containing two files:
*   `whatpylib-0.1.0.tar.gz` (Source archive)
*   `whatpylib-0.1.0-py3-none-any.whl` (Wheel file)

## Step 3: Check the Package (Optional)

You can verify the package description renders correctly:

```bash
twine check dist/*
```

## Step 4: Upload to PyPI

Use `twine` to upload the files to PyPI.

```bash
twine upload dist/*
```

You will be prompted for a username and password:
*   **Username**: `__token__`
*   **Password**: Your PyPI API token (starts with `pypi-`)

## Step 5: Verify Installation

Once uploaded, you can install your package from anywhere:

```bash
pip install whatpylib
```

## Automating with GitHub Actions (Optional)

You can automate this process using GitHub Actions. Create a file `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  pypi-publish:
    name: Upload release to PyPI
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.10"
      - name: Install build dependencies
        run: pip install build
      - name: Build package
        run: python -m build
      - name: Publish package distributions to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

**Note**: You'll need to configure "Trusted Publishing" on PyPI to use this GitHub Action without a token.
