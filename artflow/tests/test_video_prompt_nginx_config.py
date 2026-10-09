"""Full canonical Nginx syntax check with isolated, synthetic TLS fixtures.

Local fixture tests need OpenSSL, not Docker. CI additionally pre-pulls the
official Compose image and sets APIX_TEST_NGINX_IMAGE=nginx:alpine. An explicitly
enabled Docker check must fail, never skip, if Docker or validation is broken.
No production certificates, secrets, networks, services or ports are used.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_IMAGE = "nginx:alpine"
CERT_ROOT = Path("/etc/letsencrypt")
CONFIG_FILES = {"default.conf": "nginx.conf", "media.conf": "nginx-media.conf"}


def _runtime_hosts(config: str) -> list[str]:
    pools = set(re.findall(r"\bupstream\s+([\w-]+)\s*\{", config))
    hosts = set(re.findall(r"\bproxy_pass\s+https?://([\w.-]+)(?=[:/;])", config))
    hosts.update(re.findall(r"^\s*server\s+([\w.-]+):\d+\s*;", config, re.M))
    aliases = []
    for host in sorted(hosts - pools):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            aliases.append(host)
    return aliases


def _prepare_fixture(directory: Path) -> tuple[Path, Path, list[str]]:
    conf_dir = directory / "conf.d"
    tls_dir = directory / "letsencrypt"
    conf_dir.mkdir()
    tls_dir.mkdir()
    texts = []
    for destination, source in CONFIG_FILES.items():
        content = (ROOT / source).read_bytes()
        (conf_dir / destination).write_bytes(content)
        texts.append(content.decode("utf-8"))
    config = "\n".join(texts)

    cert = directory / "synthetic-cert.pem"
    key = directory / "synthetic-key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256",
         "-days", "1", "-subj", "/CN=nginx-syntax-fixture.invalid",
         "-keyout", str(key), "-out", str(cert)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    references = re.findall(r"^\s*ssl_certificate(_key)?\s+([^;\s]+)\s*;", config, re.M)
    assert references, "Canonical TLS config must supply certificate references"
    for is_key, location in references:
        relative = Path(location).relative_to(CERT_ROOT)
        assert ".." not in relative.parts, "TLS fixtures must stay in their temporary mount"
        destination = tls_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(key if is_key else cert, destination)
    return conf_dir, tls_dir, _runtime_hosts(config)


def _docker_command(image: str, conf_dir: Path, tls_dir: Path, hosts: list[str]) -> list[str]:
    # Refuse arbitrary images even if supplied through the test environment.
    assert image == OFFICIAL_IMAGE, "Use the official production Compose image"
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx_service = re.search(r"^  nginx:\n(?P<body>(?:    .*\n|\n)+)", compose, re.M)
    assert nginx_service is not None
    assert re.search(rf"^    image:\s*{re.escape(image)}\s*$", nginx_service["body"], re.M)
    command = ["docker", "run", "--rm", "--pull", "never", "--network", "none",
               "--entrypoint", "nginx",
               "--mount", f"type=bind,src={conf_dir},dst=/etc/nginx/conf.d,readonly",
               "--mount", f"type=bind,src={tls_dir},dst=/etc/letsencrypt,readonly"]
    for host in hosts:
        command.extend(["--add-host", f"{host}:127.0.0.1"])
    return [*command, image, "-t"]


def test_nginx_fixture_hostname_discovery_excludes_pool_names_and_ip_addresses() -> None:
    config = """
upstream pool {
    server backend.invalid:443;
}
server {
    location /one { proxy_pass http://pool; }
    location /two { proxy_pass http://app:8000; }
    location /three { proxy_pass http://127.0.0.1:8000; }
}
"""
    assert _runtime_hosts(config) == ["app", "backend.invalid"]


def test_nginx_fixture_preserves_full_configs_and_supplies_synthetic_tls(tmp_path) -> None:
    conf_dir, tls_dir, hosts = _prepare_fixture(tmp_path)
    for destination, source in CONFIG_FILES.items():
        assert (conf_dir / destination).read_bytes() == (ROOT / source).read_bytes()
    # Local proof of matching, readable fixture certificates and keys. This is
    # fixture validation only; Docker below performs actual Nginx validation.
    for certificate in tls_dir.rglob("fullchain.pem"):
        public_cert = subprocess.run(
            ["openssl", "x509", "-in", str(certificate), "-pubkey", "-noout"],
            check=True, capture_output=True, timeout=10,
        ).stdout
        public_key = subprocess.run(
            ["openssl", "pkey", "-in", str(certificate.with_name("privkey.pem")), "-pubout"],
            check=True, capture_output=True, timeout=10,
        ).stdout
        assert public_cert == public_key
    command = _docker_command(OFFICIAL_IMAGE, conf_dir, tls_dir, hosts)
    assert command[:8] == ["docker", "run", "--rm", "--pull", "never", "--network", "none", "--entrypoint"]
    assert command[-2:] == [OFFICIAL_IMAGE, "-t"]
    assert "--publish" not in command and "-p" not in command
    assert "app:127.0.0.1" in command
    assert "tanyapi.chillcreative.ru:127.0.0.1" in command
    assert all(str(tmp_path) in argument for argument in command if argument.startswith("type=bind,"))


@pytest.mark.parametrize("invalid_directive", [False, True], ids=["canonical", "reject-route-typo"])
def test_canonical_nginx_syntax_in_official_image(tmp_path, invalid_directive) -> None:
    image = os.environ.get("APIX_TEST_NGINX_IMAGE")
    if not image:
        pytest.skip("Set APIX_TEST_NGINX_IMAGE=nginx:alpine after pre-pulling the official image")
    assert shutil.which("docker"), "Docker is required when APIX_TEST_NGINX_IMAGE is set"
    conf_dir, tls_dir, hosts = _prepare_fixture(tmp_path)
    if invalid_directive:
        config_path = conf_dir / "default.conf"
        config = config_path.read_text(encoding="utf-8")
        assert "client_max_body_size 101M;" in config
        config_path.write_text(config.replace("client_max_body_size 101M;", "video_prompt_invalid_directive 101M;", 1), encoding="utf-8")
    result = subprocess.run(
        _docker_command(image, conf_dir, tls_dir, hosts),
        capture_output=True, text=True, timeout=60,
    )
    output = result.stdout + result.stderr
    if invalid_directive:
        assert result.returncode != 0, output
        assert 'unknown directive "video_prompt_invalid_directive"' in output, output
    else:
        assert result.returncode == 0, output
        assert "syntax is ok" in output and "test is successful" in output, output
