import os
import time
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

def load_private_key(file_path: str):
    with open(file_path, "rb") as key_file:
        return load_private_key_from_string(key_file.read())

def load_private_key_from_string(key_data: bytes):
    private_key = serialization.load_pem_private_key(
        key_data,
        password=None,
    )
    return private_key

def sign_request(private_key, timestamp: int, method: str, path: str) -> str:
    msg_string = str(timestamp) + method + path
    signature = private_key.sign(
        msg_string.encode('utf-8'),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get_auth_headers(method: str, path: str) -> dict:
    key_id = os.environ.get("KALSHI_KEY_ID")
    
    if not key_id:
        raise ValueError("KALSHI_KEY_ID must be set in environment variables.")

    private_key_content = os.environ.get("KALSHI_PRIVATE_KEY")
    if private_key_content:
        # In case the newlines were literally escaped backslashes as typical in some env setups
        private_key_content = private_key_content.replace("\\n", "\n")
        private_key = load_private_key_from_string(private_key_content.encode('utf-8'))
    else:
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not key_path:
            raise ValueError("Either KALSHI_PRIVATE_KEY or KALSHI_PRIVATE_KEY_PATH must be set in environment variables.")
        private_key = load_private_key(key_path)
    timestamp = int(time.time() * 1000)
    
    signature = sign_request(private_key, timestamp, method, path)

    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp)
    }
