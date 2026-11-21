# Your QuantDesk repo — safe integration

We have historical notes of `C:\ai projects\quant_desk`, Python package `quantdesk`, v0.6.1 with SQLite journal, kill switch and prior 127 passing tests. **We have not inspected the current working tree** or verified whether you progressed beyond v0.6.1; therefore this zip is an additive research module, not an in-place repo modification.

Suggested shell commands after extraction and after making a Git checkpoint:

```powershell
cd "C:\ai projects\quant_desk"
git status --short
git add -A
git commit -m "checkpoint before market structure experiment"  # only if intended changes reviewed
# In File Explorer, copy market_structure_lab/ and tests_market_structure/ from the extracted archive to this repo root.
python -m unittest discover -s tests_market_structure -v
python -m unittest discover -s tests -v
python -m market_structure_lab.run --data-dir data --out outputs/market_structure_v01
```

If `python` resolves to a different interpreter, use your project's venv Python instead. Note: no real bar CSVs are included. Export prior Alpaca data or run the optional downloader.

Until you provide the actual Git repository or zip, don't assume an import path into existing QuantDesk CLI or broker infrastructure. Focus on scientific auditability: preserve the CSV data/source, config JSON, and report in a research-only branch.
