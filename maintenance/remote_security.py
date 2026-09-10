"""Per-installation TLS material for the authenticated peer socket."""

from __future__ import annotations

import hashlib
import os
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TLSMaterial:
    certificate: Path
    private_key: Path
    fingerprint: str


def ensure_tls_material(directory: Path, node_id: str) -> TLSMaterial:
    directory.mkdir(parents=True, exist_ok=True)
    certificate = directory / "peer-tls.crt"
    private_key = directory / "peer-tls.key"
    if not certificate.exists() or not private_key.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "3650",
                "-subj",
                f"/CN={node_id}",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    os.chmod(private_key, 0o600)
    os.chmod(certificate, 0o644)
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="ascii"))
    digest = hashlib.sha256(der).hexdigest()
    fingerprint = ":".join(digest[index : index + 4] for index in range(0, 64, 4))
    return TLSMaterial(certificate, private_key, fingerprint)


def server_context(material: TLSMaterial) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(material.certificate, material.private_key)
    return context


def client_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
