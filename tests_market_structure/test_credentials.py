"""Offline credential-handling tests. No genuine secrets, Windows vault, or network."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from market_structure_lab import credentials as c


class FakeVault:
    def __init__(self):
        self.items = {}
        self.reads = 0

    def set_password(self, service, account, value):
        self.items[(service, account)] = value

    def get_password(self, service, account):
        self.reads += 1
        return self.items.get((service, account))

    def delete_password(self, service, account):
        del self.items[(service, account)]


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.vault = FakeVault()

    def test_save_and_lookup_without_environment_or_disk(self):
        c.save_pair('FAKE_PAPER_ID', 'FAKE_PAPER_SECRET', vault=self.vault)
        result = c.get_alpaca_credentials(environment={}, vault=self.vault)
        self.assertEqual(result, ('FAKE_PAPER_ID', 'FAKE_PAPER_SECRET'))
        self.assertEqual(len(self.vault.items), 1)
        self.assertEqual(json.loads(next(iter(self.vault.items.values())))['key_id'], 'FAKE_PAPER_ID')

    def test_complete_environment_pair_overrides_saved_pair(self):
        c.save_pair('saved-id', 'saved-secret', vault=self.vault)
        self.assertEqual(c.get_alpaca_credentials(
            environment={'APCA_API_KEY_ID':'ephemeral-id', 'APCA_API_SECRET_KEY':'ephemeral-secret'},
            vault=self.vault), ('ephemeral-id', 'ephemeral-secret'))
        self.assertEqual(self.vault.reads, 0)

    def test_partial_environment_pair_fails_closed_without_fallback(self):
        c.save_pair('saved-id', 'saved-secret', vault=self.vault)
        for partial in ({'APCA_API_KEY_ID':'id-only'}, {'APCA_API_SECRET_KEY':'secret-only'}):
            with self.subTest(partial=partial), self.assertRaises(c.CredentialError):
                c.get_alpaca_credentials(environment=partial, vault=self.vault)
        self.assertEqual(self.vault.reads, 0)

    def test_missing_corrupt_and_empty_records_fail_closed(self):
        with self.assertRaises(c.CredentialError):
            c.get_alpaca_credentials(environment={}, vault=self.vault)
        for blob in ('{', '{}', '"secret"', json.dumps({'key_id': 'id', 'secret_key':''})):
            self.vault.items[(c.SERVICE,c.ACCOUNT)] = blob
            with self.subTest(blob=blob), self.assertRaises(c.CredentialError):
                c.get_alpaca_credentials(environment={}, vault=self.vault)

    def test_delete_removes_only_our_record(self):
        c.save_pair('id', 'secret', vault=self.vault)
        self.vault.items[('unrelated', 'other')] = 'keep'
        self.assertTrue(c.vault_has_pair(vault=self.vault))
        c.erase_pair(vault=self.vault)
        self.assertFalse(c.vault_has_pair(vault=self.vault))
        self.assertEqual(self.vault.items[('unrelated','other')], 'keep')

    def test_status_never_logs_stored_secret(self):
        c.save_pair('PRIVATE-KEY-ID', 'PRIVATE-SECRET', vault=self.vault)
        output = io.StringIO()
        with patch.object(c, '_windows_vault', return_value=self.vault), patch.dict(c.os.environ, {}, clear=True), redirect_stdout(output):
            self.assertEqual(c.main(['status']), 0)
        self.assertIn('present', output.getvalue())
        self.assertNotIn('PRIVATE-KEY-ID', output.getvalue())
        self.assertNotIn('PRIVATE-SECRET', output.getvalue())

    def test_save_cli_uses_hidden_prompt_and_prints_no_secrets(self):
        output = io.StringIO()
        with patch.object(c, '_windows_vault', return_value=self.vault), patch.object(c, 'getpass', side_effect=['HIDDEN-ID', 'HIDDEN-SECRET']), redirect_stdout(output):
            self.assertEqual(c.main(['save']), 0)
        self.assertNotIn('HIDDEN-ID', output.getvalue())
        self.assertNotIn('HIDDEN-SECRET', output.getvalue())
        self.assertTrue(c.vault_has_pair(vault=self.vault))

    def test_incomplete_env_not_leaked_in_error(self):
        with self.assertRaises(c.CredentialError) as captured:
            c.get_alpaca_credentials(environment={'APCA_API_KEY_ID':'DO-NOT-PRINT-THIS'}, vault=self.vault)
        self.assertNotIn('DO-NOT-PRINT-THIS', str(captured.exception))


if __name__ == '__main__':
    unittest.main()
