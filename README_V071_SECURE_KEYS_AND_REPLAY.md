# QuantDesk v0.7.1 — Secure paper credentials + replay quality-of-life

This is a presentation and authentication-convenience patch atop **QuantDesk v0.7**, not an order-execution release. It keeps all market math and research safety checks untouched.

## What's new

- The six Alpaca historical-data entry points and the opt-in read-only live observer now ask a shared credentials resolver for a key pair.
- **First:** use a complete `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY` environment pair, if set in the current process.
- **Otherwise:** read the **paper-trading** pair from this Windows user's **Windows Credential Manager** using the Python `keyring` library.
- A partial environment pair is rejected rather than mixing an environment key with a saved key.
- No `.env` file, code-level secret constant, credential JSON in the repository, browser storage, or plaintext local config is created.
- `save`, `status`, and `delete` commands never print the key ID or secret. **The `save` prompt hides both values**.
- Historical Replay now opens the **last completed intraday bar** when you switch to an intraday timeframe. `Last date` now goes to the latest **session and its last bar**, including when you're already on that session.
- Adds 6×, 8× and 10× playback speeds, with distinct target intervals (approximately 137, 103 and 82 milliseconds per bar). Actual playback can be slower if the local API or rendering cannot keep up.

## Initial setup — once per Windows account

In the existing QuantDesk project, while using your regular Windows user profile:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m market_structure_lab.credentials save
```

Paste the **paper-trading API Key ID** and **paper-trading secret key** when prompted. Neither entry is echoed; don't record or share the prompts. This writes a single encrypted credential entry inside Windows Credential Manager (service `QuantDesk/Alpaca/Paper`, account `paper-key-pair`). It is **not a project file**.

Verify the saved record exists **without revealing keys**:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.credentials status
```

Now close and reopen PowerShell. You **do not need to set environment variables**. Run the workstation or any supported read-only data CLI normally. For example:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive download --symbols SPY --start 2026-09-30 --end 2026-09-30 --feed sip --kind bars
```

`--enable-live` remains explicit, and **never turns on automatically** just because credentials are saved. The patch does not connect to Alpaca unless you invoke a data-fetch command or enable read-only live observation.

## Existing temporary PowerShell variables

If you previously set one or both environment variables in your current PowerShell window, they take precedence (or a partial pair blocks startup). Open a new terminal, or remove **only the temporary variables in the current terminal**:

```powershell
Remove-Item Env:\APCA_API_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:\APCA_API_SECRET_KEY -ErrorAction SilentlyContinue
```

Never use `setx` to persist API secrets as plain user environment values.

## Rotation and deletion

After changing keys in Alpaca, run `python -m market_structure_lab.credentials save` again to replace the pair. To delete **only** QuantDesk's saved paper credential record:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.credentials delete
```

You must type `DELETE` at the prompt.

## Security boundaries (important)

- Windows Credential Manager encrypts stored credentials for your Windows user, but **it does not make the secrets inaccessible to every program running as that same user**. A local AI coding agent with terminal access under your Windows login could potentially retrieve them, as could malware running under your account. Do not grant untrusted local agents access to this vault or execute unreviewed scripts as that user.
- Code changes are open for inspection; the ZIP contains **no real keys**. Never include keys, local exports, vault backups, environment dumps, or tokens in Git commits or screenshots.
- The user must supply keys locally after installation; nothing in this patch sends them to OpenAI, a chat session, GitHub, or the browser. An explicitly started Alpaca request necessarily sends its authentication headers to Alpaca.
- Existing trading API key pairs may authorize account actions even though **QuantDesk itself provides no broker order endpoint**. Keep this to **paper** credentials until an explicit permissions model exists.
- Credentials are not tested against Alpaca during setup, and internet access is not required. Correctness of real entitlements must still be verified with a read-only download.
- This patch is for Windows only when using the vault; environment-variable behavior remains available on other OSes.

## Validation

We ran `python -m unittest discover -s tests_market_structure -v` on an assembled v0.7 development copy: **101 tests passed**. This includes eight local credential-resolver tests and three replay UX tests. The library's real Windows Credential Manager integration was **not tested on your Windows installation**, and headless Chromium here is blocked from the local website. A real browser smoke check should be done on your machine.

No KDE, profile, regime, or experiment formulas were changed. No order/trading functions added.
