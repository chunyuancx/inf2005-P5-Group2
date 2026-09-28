from src.models.payload import Payload
from src.services.crypto_service import CryptoService

def test_crypto_lifecycle_and_tampering():
    # Setup keys for two distinct entities
    private_key_A, public_key_A = CryptoService.generate_key_pair()
    private_key_B, public_key_B = CryptoService.generate_key_pair()
    
    # Payload setup
    payload = Payload(metadata={"classification": "confidential"})
    data = payload.get_serializable_data()
    
    # 1. Hashing Check
    hash_value = CryptoService.generate_hash(data)
    assert len(hash_value) == 32  # SHA-256 produces a 32-byte hash
    
    # 2. Positive Test: Authentic Signature
    signature = CryptoService.sign_payload(private_key_A, data)
    assert CryptoService.verify_signature(public_key_A, signature, data) is True
    
    # 3. Negative Test: Wrong Key (Signed by A, verified by B)
    assert CryptoService.verify_signature(public_key_B, signature, data) is False
    
    # 4. Negative Test: Tampered Data (Data altered after signing)
    tampered_data = data + b"malicious_alteration"
    assert CryptoService.verify_signature(public_key_A, signature, tampered_data) is False
    
    # 5. Negative Test: Wrong/Corrupted Signature
    wrong_signature = CryptoService.sign_payload(private_key_A, tampered_data)
    assert CryptoService.verify_signature(public_key_A, wrong_signature, data) is False