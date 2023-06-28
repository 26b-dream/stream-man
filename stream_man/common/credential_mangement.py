# I don't usually copy and paste code but encrypting secrets is one of the few situations where I will take a snippet
# written by somone else that has been vetted by the community
# See: https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
import json
import secrets
from base64 import urlsafe_b64decode as b64d
from base64 import urlsafe_b64encode as b64e

from common.constants import BASE_DIR
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BACKEND = default_backend()
ITERATIONS = 100_000
CREDENTIALS_FILE = BASE_DIR / "credentials.encrypted"


def _derive_key(password: bytes, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    """Derive a secret key from a given password and salt"""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations, backend=BACKEND)
    return b64e(kdf.derive(password))


def _password_encrypt(message: bytes, password: str, iterations: int = ITERATIONS) -> bytes:
    salt = secrets.token_bytes(16)
    key = _derive_key(password.encode(), salt, iterations)
    return b64e(
        b"%b%b%b"
        % (
            salt,
            iterations.to_bytes(4, "big"),
            b64d(Fernet(key).encrypt(message)),
        )
    )


def _password_decrypt(token: bytes, password: str) -> bytes:
    decoded = b64d(token)
    salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
    iterations = int.from_bytes(iter, "big")
    key = _derive_key(password.encode(), salt, iterations)
    return Fernet(key).decrypt(token)


def dump_credentials(credentials: dict[str, dict[str, str]], password: str) -> None:
    """Dump credentials to disk"""
    dumped_credentials = json.dumps(credentials)
    encrypted_credentials = _password_encrypt(dumped_credentials.encode(), password)
    CREDENTIALS_FILE.write(encrypted_credentials)


def load_credentials(password: str) -> dict[str, dict[str, str]]:
    encrypted_credential = CREDENTIALS_FILE.read_bytes()
    decrypted_credentials = _password_decrypt(encrypted_credential, password)
    return json.loads(decrypted_credentials)
