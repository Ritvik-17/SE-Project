"""Development TLS certificate for HTTPS on localhost (step 17, encryption in transit).

  python -m app.security.devcert        writes certs/localhost.pem and certs/localhost-key.pem (git-ignored)

Then run the API over HTTPS:
  .venv\\Scripts\\uvicorn app.api.main:app --reload --ssl-certfile certs/localhost.pem --ssl-keyfile certs/localhost-key.pem
and the UI with RERA_HTTPS=1 (Vite serves https://localhost:5173 and proxies to https://localhost:8000).
Browsers warn about a self-signed certificate; trust it locally or use a tool such as mkcert. In production TLS is
terminated by a reverse proxy or load balancer with a CA-issued certificate, COOKIE_SECURE=true and HSTS.
"""

import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

OUT = Path(__file__).resolve().parents[2] / "certs"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=397))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    (OUT / "localhost-key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                               serialization.NoEncryption()))
    (OUT / "localhost.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Wrote {OUT / 'localhost.pem'} and {OUT / 'localhost-key.pem'}")


if __name__ == "__main__":
    main()
