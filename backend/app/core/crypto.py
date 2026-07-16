from cryptography.fernet import Fernet, InvalidToken

class CryptoError(ValueError):
    pass

class CryptoService:
    """Fernet-backed API key encryption.

    Fernet provides authenticated symmetric encryption over AES-CBC + HMAC. It
    is the cryptography project's safe recipe and satisfies the Fernet
    requirement for encrypted-at-rest provider secrets.
    """
    def __init__(self, key: str):
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as exc:
            raise CryptoError("Invalid ENCRYPTION_KEY; generate one with Fernet.generate_key()") from exc

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise CryptoError("API key cannot be empty")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise CryptoError("Could not decrypt API key; ENCRYPTION_KEY may have changed") from exc
