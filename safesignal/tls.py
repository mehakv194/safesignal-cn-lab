"""Locally generated development certificate; verification is always enabled."""
import ipaddress
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path


def create_certificate(directory, valid_days=30):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    stamp = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(stamp - timedelta(minutes=1))
            .not_valid_after(stamp + timedelta(days=valid_days))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .sign(key, hashes.SHA256()))
    (directory / 'server.key').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    (directory / 'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def server_context(directory):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(Path(directory) / 'server.pem'), str(Path(directory) / 'server.key'))
    return context


def client_context(directory):
    return ssl.create_default_context(cafile=str(Path(directory) / 'server.pem'))
