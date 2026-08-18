import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.crypto import decrypt_secret, encrypt_secret, encryption_configured


class TestCrypto(unittest.TestCase):
    def test_encryption_configured_reflects_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(encryption_configured())
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": Fernet.generate_key().decode()}):
            self.assertTrue(encryption_configured())

    def test_encrypt_decrypt_round_trip(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            ciphertext = encrypt_secret("super-secret-token")
            self.assertTrue(ciphertext.startswith("fernet:"))
            self.assertNotIn("super-secret-token", ciphertext)
            self.assertEqual(decrypt_secret(ciphertext), "super-secret-token")

    def test_encrypt_is_noop_when_key_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(encrypt_secret("plain-token"), "plain-token")

    def test_encrypt_is_noop_for_empty_string(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            self.assertEqual(encrypt_secret(""), "")

    def test_decrypt_passes_through_legacy_plaintext(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            self.assertEqual(decrypt_secret("plain-legacy-token"), "plain-legacy-token")

    def test_decrypt_returns_ciphertext_unchanged_when_key_unset(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            ciphertext = encrypt_secret("token")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(decrypt_secret(ciphertext), ciphertext)

    def test_decrypt_with_wrong_key_returns_ciphertext_unchanged(self):
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": Fernet.generate_key().decode()}):
            ciphertext = encrypt_secret("token")
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": Fernet.generate_key().decode()}):
            self.assertEqual(decrypt_secret(ciphertext), ciphertext)

    def test_encrypt_does_not_double_encrypt(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"HIVE_SECRET_KEY": key}):
            once = encrypt_secret("token")
            twice = encrypt_secret(once)
            self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
