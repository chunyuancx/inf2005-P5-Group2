import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

class CryptoService:
    @staticmethod
    def generate_key_pair():
        """Generates an RSA-2048 private and public key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        return private_key, private_key.public_key()

    @staticmethod
    def generate_hash(data: bytes) -> bytes:
        """Generates a SHA-256 hash of the payload."""
        return hashlib.sha256(data).digest()

    @staticmethod
    def sign_payload(private_key, data: bytes) -> bytes:
        """Signs the data using the private key and secure PSS padding."""
        return private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

    @staticmethod
    def verify_signature(public_key, signature: bytes, data: bytes) -> bool:
        """Verifies the signature against the data using the public key."""
        try:
            public_key.verify(
                signature,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False