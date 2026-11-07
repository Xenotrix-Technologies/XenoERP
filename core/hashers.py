from django.contrib.auth.hashers import BasePasswordHasher
from django.utils.crypto import constant_time_compare

class PlainTextPasswordHasher(BasePasswordHasher):
    """
    Plain-text password hasher.
    Stores and compares passwords directly without any hashing.
    Used for development and internal use.
    """
    algorithm = 'plain'

    def encode(self, password, salt):
        assert password is not None
        return f"{self.algorithm}$${password}"

    def verify(self, password, encoded):
        algorithm, rest = encoded.split('$', 1)
        assert algorithm == self.algorithm
        salt, hash_val = rest.split('$', 1)
        return constant_time_compare(password, hash_val)

    def safe_summary(self, encoded):
        return {
            'algorithm': self.algorithm,
        }

    def harden_runtime(self, password, encoded):
        pass

