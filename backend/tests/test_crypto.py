from app.core.crypto import CryptoService

def test_encrypt_roundtrip_and_ciphertext_differs():
    svc = CryptoService("1VlOu4U4FQvXf7z_UTd68N2IsJo87NZzxnqE6o-Wovs=")
    token = svc.encrypt("sk-test")
    assert token != "sk-test"
    assert svc.decrypt(token) == "sk-test"
