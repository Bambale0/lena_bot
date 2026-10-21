"""Full canonical Nginx syntax check with isolated, synthetic TLS fixtures.

Local fixture tests need OpenSSL, not Docker. CI additionally pre-pulls the
official Compose image and sets APIX_TEST_NGINX_IMAGE=nginx:alpine. An explicitly
enabled Docker check must fail, never skip, if Docker or validation is broken.
No production certificates, secrets, networks, services or ports are used.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import re
import shutil
import socket
import ssl
import subprocess
import time
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
    assert "banano-miniapp:127.0.0.1" in command
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


@pytest.fixture
def running_nginx(tmp_path):
    """Exercise full production vhost selection with synthetic certificates only."""
    image = os.environ.get("APIX_TEST_NGINX_IMAGE")
    if not image:
        pytest.skip("Set APIX_TEST_NGINX_IMAGE=nginx:alpine for real Nginx HTTP/TLS checks")
    conf_dir, tls_dir, hosts = _prepare_fixture(tmp_path)
    webroot = tmp_path / "webroot"
    challenge = webroot / ".well-known" / "acme-challenge" / "fixture-probe"
    challenge.parent.mkdir(parents=True)
    challenge.write_text("acme-fixture-ok")
    command = _docker_command(image, conf_dir, tls_dir, hosts)
    # Only synthetic inputs; random loopback ports avoid all production listeners.
    command[command.index("none")] = "bridge"
    command[2:2] = ["--detach"]
    command[-2:] = [
        "--publish", "127.0.0.1::80", "--publish", "127.0.0.1::443",
        "--mount", f"type=bind,src={webroot},dst=/var/www/certbot,readonly",
        image, "-g", "daemon off;",
    ]
    container = subprocess.check_output(command, text=True, timeout=30).strip()
    try:
        def port(number):
            result = subprocess.check_output(
                ["docker", "port", container, str(number)], text=True, timeout=10,
            )
            return int(result.strip().rsplit(":", 1)[1])

        http_port, tls_port = port(80), port(443)
        for attempt in range(50):
            try:
                with socket.create_connection(("127.0.0.1", http_port), timeout=1):
                    break
            except OSError:
                if attempt == 49:
                    pytest.fail("Synthetic Nginx did not start")
                time.sleep(0.1)
        yield http_port, tls_port, tmp_path / "synthetic-cert.pem"
    finally:
        subprocess.run(["docker", "stop", "--time", "1", container], check=True,
                       capture_output=True, timeout=15)


@pytest.mark.parametrize("host", [
    "apixbotai.com", "testapi.chillcreative.ru", "apix.chillcreative.ru",
    "media.apixbotai.com", "tbank.apixbotai.com", "alena.chillcreative.ru",
    "alena.xn--e1aikcel5c5a.online", "archibot.xn--e1aikcel5c5a.online",
])
def test_active_hosts_serve_http01_without_redirect(running_nginx, host):
    connection = http.client.HTTPConnection("127.0.0.1", running_nginx[0], timeout=5)
    try:
        connection.request("GET", "/.well-known/acme-challenge/fixture-probe",
                           headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"acme-fixture-ok"
    finally:
        connection.close()
    if host != "archibot.xn--e1aikcel5c5a.online":  # This legacy route is HTTP-only.
        context = ssl.create_default_context(cafile=str(running_nginx[2]))
        context.check_hostname = False  # All synthetic certificates use a fixture CN.
        with socket.create_connection(("127.0.0.1", running_nginx[1]), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                assert tls.getpeercert()


@pytest.mark.parametrize("host", [
    "xn--e1aikcel5c5a.online", "www.xn--e1aikcel5c5a.online",
    "tanyapp.chillcreative.ru", "unknown.invalid",
])
def test_retired_and_unknown_hosts_do_not_reach_applications(running_nginx, host):
    connection = http.client.HTTPConnection("127.0.0.1", running_nginx[0], timeout=5)
    try:
        connection.request("GET", "/", headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 404
        response.read()
    finally:
        connection.close()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # Synthetic fixture certificates only.
    with socket.create_connection(("127.0.0.1", running_nginx[1]), timeout=5) as raw:
        with pytest.raises(ssl.SSLError):
            context.wrap_socket(raw, server_hostname=host)
