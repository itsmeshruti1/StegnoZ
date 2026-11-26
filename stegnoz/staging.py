"""Authenticated private staging; the random run key exists only in memory."""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedStaging:
    def __init__(self):
        self._cipher = AESGCM(AESGCM.generate_key(bit_length=256))
        self._counter = 0

    def write(self, path, data):
        # Each write, including a policy retry, gets a fresh nonce under this key.
        self._counter += 1
        nonce = self._counter.to_bytes(12, "big")
        ciphertext = self._cipher.encrypt(nonce, data, path.name.encode("utf-8"))
        path.write_bytes(nonce + ciphertext)

    def read(self, path):
        data = path.read_bytes()
        return self._cipher.decrypt(data[:12], data[12:], path.name.encode("utf-8"))
