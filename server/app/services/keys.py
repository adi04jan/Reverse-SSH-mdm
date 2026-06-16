"""Ed25519 keypair generation for device tunnels."""
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass
class KeyPair:
    private_openssh: str  # PEM-style OpenSSH private key (goes to the device)
    public_openssh: str   # single-line OpenSSH public key (stored on the server)


def generate_keypair(comment: str = "") -> KeyPair:
    key = Ed25519PrivateKey.generate()

    private_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    public_line = public_bytes.decode("utf-8")
    if comment:
        public_line = f"{public_line} {comment}"

    return KeyPair(
        private_openssh=private_bytes.decode("utf-8"),
        public_openssh=public_line,
    )
