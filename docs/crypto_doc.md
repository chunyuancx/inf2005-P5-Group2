# Cryptography & Payload Specification
Done by: Randy Kwok (Member 3)
This module manages the payload structure, integrity hashing, and authenticity verification for the steganography pipeline.

*   **Prerequisites:** Requires the `cryptography` Python package (`pip install cryptography`).
*   **Payload Structure:** Bundles a `media_id` (UUID), `timestamp` (float), `nonce` (16-character hex), and `metadata`. It must be serialized to JSON via `get_serializable_data()` to ensure deterministic byte generation for hashing.
*   **Hashing:** Implements SHA-256. The Verification Engine must re-hash the extracted payload and compare it against the embedded hash.
*   **Signatures:** Utilizes RSA-2048 with PSS padding and SHA-256. Members 1 and 2 will embed the payload bytes alongside the signature. Member 5 will invoke `CryptoService.verify_signature(public_key, signature, data)` during the extraction workflow to authenticate the sender.