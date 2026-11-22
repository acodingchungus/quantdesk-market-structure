"""Alpaca *paper* credentials: Windows Credential Manager, no secrets in repo.

Environment variables remain supported for existing CLI/CI workflows. A complete
pair of temporary environment variables overrides the Windows vault, but a
partial pair is rejected rather than silently mixing unrelated credentials.

No key material is written to the project folder, logs, Git, or browser API.
This module does not make network requests or enable broker orders.
"""
from __future__ import annotations

import argparse
from getpass import getpass
import json
import os

SERVICE = "QuantDesk/Alpaca/Paper"
ACCOUNT = "paper-key-pair"


class CredentialError(RuntimeError):
    """Actionable error without exposing API key material."""


def _windows_vault():
    if os.name != "nt":
        raise CredentialError("Secure saved credentials are Windows-only. On other systems use environment variables.")
    try:
        import keyring
        from keyring.backends.Windows import WinVaultKeyring
        backend = keyring.get_keyring()
        if not isinstance(backend, WinVaultKeyring):
            raise CredentialError(
                "Secure Windows Credential Manager backend is unavailable. "
                "Refusing to use a potentially insecure keyring backend."
            )
        return backend
    except ImportError as exc:
        raise CredentialError("Install Windows credential support: .\\.venv\\Scripts\\python.exe -m pip install keyring") from None
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Could not access Windows Credential Manager; check Windows user permissions.") from None


def _decode_pair(blob: str | None) -> tuple[str, str] | None:
    if not blob:
        return None
    try:
        pair = json.loads(blob)
        key = pair["key_id"]
        secret = pair["secret_key"]
        if not isinstance(key, str) or not isinstance(secret, str) or not key.strip() or not secret.strip():
            raise ValueError("Empty or invalid credential")
        return key.strip(), secret.strip()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CredentialError("Saved Alpaca credential record is invalid. Run: python -m market_structure_lab.credentials save") from None


def get_alpaca_credentials(*, environment=None, vault=None) -> tuple[str, str]:
    """Return complete Alpaca key pair, never log/print it.

    Explicit environment pair takes precedence. Do not combine one environment
    key with one Windows-vault key. If environment vars are absent, use vault.
    The vault can be injected for pure offline unit tests.
    """
    env = os.environ if environment is None else environment
    key = (env.get("APCA_API_KEY_ID") or "").strip()
    secret = (env.get("APCA_API_SECRET_KEY") or "").strip()
    if key or secret:
        if not key or not secret:
            raise CredentialError("Only one APCA environment variable is set. Set both, or unset both to use Windows Credential Manager.")
        return key, secret
    try:
        secure_store = vault if vault is not None else _windows_vault()
        pair = _decode_pair(secure_store.get_password(SERVICE, ACCOUNT))
        if pair:
            return pair
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Unable to read the saved Alpaca paper keys from Windows Credential Manager.") from None
    raise CredentialError("No Alpaca paper credentials saved. Run: .\\.venv\\Scripts\\python.exe -m market_structure_lab.credentials save")


def save_pair(key_id: str, secret_key: str, *, vault=None) -> None:
    if not isinstance(key_id, str) or not isinstance(secret_key, str):
        raise CredentialError("Key ID and secret must be non-empty text")
    key_id, secret_key = key_id.strip(), secret_key.strip()
    if not key_id or not secret_key:
        raise CredentialError("Key ID and secret must not be empty")
    try:
        secure_store = vault if vault is not None else _windows_vault()
        secure_store.set_password(SERVICE, ACCOUNT, json.dumps({"key_id": key_id, "secret_key": secret_key}))
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Could not save credentials to Windows Credential Manager.") from None


def erase_pair(*, vault=None) -> None:
    try:
        secure_store = vault if vault is not None else _windows_vault()
        secure_store.delete_password(SERVICE, ACCOUNT)
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Could not delete the Windows Credential Manager record (it may not exist).") from None


def vault_has_pair(*, vault=None) -> bool:
    try:
        secure_store = vault if vault is not None else _windows_vault()
        return _decode_pair(secure_store.get_password(SERVICE, ACCOUNT)) is not None
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Could not inspect Windows Credential Manager.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Save QuantDesk Alpaca PAPER keys in Windows Credential Manager; never writes .env files")
    parser.add_argument("command", choices=("save", "status", "delete"), help="All commands are local; no Alpaca API request")
    args = parser.parse_args(argv)
    try:
        if args.command == "save":
            print("Only use your Alpaca PAPER TRADING key pair. Neither value will be echoed.")
            key_id = getpass("Paper API Key ID (hidden): ")
            secret_key = getpass("Paper API Secret Key (hidden): ")
            save_pair(key_id, secret_key)
            # Don't read back or display any part of the credentials.
            print("Saved in this Windows user's Credential Manager; no project file was created.")
        elif args.command == "status":
            env = os.environ
            if env.get("APCA_API_KEY_ID") or env.get("APCA_API_SECRET_KEY"):
                if not (env.get("APCA_API_KEY_ID") and env.get("APCA_API_SECRET_KEY")):
                    print("A partial environment pair is set and will block use of the saved vault pair.")
                else:
                    print("A complete temporary environment pair is set and takes precedence for this process.")
            print("Windows Credential Manager record: " + ("present" if vault_has_pair() else "not found"))
        elif args.command == "delete":
            confirmation = input("Remove only the QuantDesk/Alpaca/Paper credential record? Type DELETE: ").strip()
            if confirmation != "DELETE":
                print("Canceled. Nothing removed.")
                return 1
            erase_pair()
            print("QuantDesk paper credentials removed from Windows Credential Manager.")
    except CredentialError as exc:
        parser.exit(2, str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
