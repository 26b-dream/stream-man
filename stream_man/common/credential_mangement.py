# I don't usually copy and paste code but encrypting secrets is one of the few situations where I will take a snippet
# written by somone else that has been vetted by the community
# See: https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
import json
import secrets
from base64 import urlsafe_b64decode as b64d
from base64 import urlsafe_b64encode as b64e
from getpass import getpass

from common.constants import BASE_DIR
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class Credentials:
    credentials: dict[str, dict[str, str]] = {}

    BACKEND = default_backend()
    ITERATIONS = 100_000
    CREDENTIALS_FILE = BASE_DIR / "credentials.encrypted"
    UNENCRYPTED_CREDENTIALS_FILE = BASE_DIR / "credentials.json"
    password = ""

    @classmethod
    def login(cls):
        if not cls.password:
            cls.password = getpass("Credentials password")

    @classmethod
    def _derive_key(cls, salt: bytes, iterations: int = ITERATIONS) -> bytes:
        """Derive a secret key from a given password and salt"""
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations, backend=cls.BACKEND)
        return b64e(kdf.derive(cls.password.encode()))

    @classmethod
    def _password_encrypt(cls, message: bytes, iterations: int = ITERATIONS) -> bytes:
        salt = secrets.token_bytes(16)
        key = cls._derive_key(salt, iterations)
        return b64e(
            b"%b%b%b"
            % (
                salt,
                iterations.to_bytes(4, "big"),
                b64d(Fernet(key).encrypt(message)),
            )
        )

    @classmethod
    def _password_decrypt(cls, token: bytes) -> bytes:
        decoded = b64d(token)
        salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
        iterations = int.from_bytes(iter, "big")
        key = cls._derive_key(salt, iterations)
        return Fernet(key).decrypt(token)

    @classmethod
    def save_credentials(cls, credentials: dict[str, dict[str, str]]) -> None:
        """Save credentials to disk"""
        dumped_credentials = json.dumps(credentials)
        encrypted_credentials = cls._password_encrypt(dumped_credentials.encode())
        cls.CREDENTIALS_FILE.write(encrypted_credentials)

    @classmethod
    def dump_credentials(cls, credentials: dict[str, dict[str, str]]) -> None:
        """Dump UNENCRYPTED credentials to disk"""
        dumped_credentials = json.dumps(credentials)
        cls.UNENCRYPTED_CREDENTIALS_FILE.write(dumped_credentials)

    @classmethod
    def import_credentials(cls) -> None:
        """Dump UNENCRYPTED credentials to disk"""
        loaded_credentials = cls.UNENCRYPTED_CREDENTIALS_FILE.read_text()
        encrypted_credentials = cls._password_encrypt(loaded_credentials.encode())
        cls.CREDENTIALS_FILE.write(encrypted_credentials)

    @classmethod
    def load_credentials(cls) -> dict[str, dict[str, str]]:
        encrypted_credential = cls.CREDENTIALS_FILE.read_bytes()
        decrypted_credentials = cls._password_decrypt(encrypted_credential)
        cls.credentials = json.loads(decrypted_credentials)
        return cls.credentials
