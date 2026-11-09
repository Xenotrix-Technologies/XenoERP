from django.contrib.auth.hashers import BasePasswordHasher
from django.utils.crypto import constant_time_compare


class PlainTextPasswordHasher(BasePasswordHasher):
    """
    A password hasher that stores passwords in plain text (no hashing).
    FOR DEVELOPMENT / INTERNAL USE ONLY — not suitable for production.
    Supports 'plaintext$$<password>', 'plain$$<password>', and raw passwords.
    """
    algorithm = "plaintext"

    def salt(self):
        return ""

    def encode(self, password, salt):
        return f"{self.algorithm}$${password}"

    def decode(self, encoded):
        if not encoded:
            return {"algorithm": self.algorithm, "hash": ""}
        if "$" in encoded:
            parts = encoded.split("$")
            # Handle format like plaintext$$password (empty salt in middle)
            password_val = parts[-1]
            return {
                "algorithm": parts[0] or self.algorithm,
                "hash": password_val,
            }
        return {
            "algorithm": self.algorithm,
            "hash": encoded,
        }

    def verify(self, password, encoded):
        if not encoded:
            return False
        decoded = self.decode(encoded)
        return constant_time_compare(password, decoded["hash"])

    def safe_summary(self, encoded):
        decoded = self.decode(encoded)
        return {
            "algorithm": decoded["algorithm"],
            "password": decoded["hash"],
        }

    def must_update(self, encoded):
        return False

    def harden_runtime(self, password, encoded):
        pass


class PlainAliasPasswordHasher(PlainTextPasswordHasher):
    """Alias hasher for 'plain$$<password>'."""
    algorithm = "plain"
