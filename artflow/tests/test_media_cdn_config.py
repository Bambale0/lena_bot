from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_media_nginx_serves_upload_volume_with_immutable_cache() -> None:
    config = (ROOT / "nginx-media.conf").read_text(encoding="utf-8")

    assert "server_name media.apixbotai.com;" in config
    assert "location ^~ /uploads/" in config
    assert "alias /var/www/apix-media/uploads/;" in config
    assert "max-age=31536000" in config
    assert "s-maxage=31536000" in config
    assert "immutable" in config
    assert 'Access-Control-Allow-Origin "*"' in config
    assert "limit_except GET HEAD" in config
    assert "/etc/letsencrypt/live/media.apixbotai.com/fullchain.pem" in config


def test_compose_mounts_media_config_and_uploads_read_only() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./nginx-media.conf:/etc/nginx/conf.d/media.conf:ro" in compose
    assert "./static/upload:/var/www/apix-media/uploads:ro" in compose


def test_media_cdn_environment_is_documented() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    config = (ROOT / "core" / "config.py").read_text(encoding="utf-8")

    assert "STATIC_UPLOAD_PUBLIC_BASE_URL=https://media.apixbotai.com" in env_example
    assert "STATIC_UPLOAD_PUBLIC_URL_PATH=/uploads" in env_example
    assert "STATIC_UPLOAD_PUBLIC_BASE_URL: str" in config
    assert "STATIC_UPLOAD_PUBLIC_URL_PATH: str" in config


def test_deploy_refuses_missing_media_certificate() -> None:
    script = (ROOT / "scripts" / "deploy-production.sh").read_text(encoding="utf-8")

    assert "MEDIA_CERT_DIR" in script
    assert "media CDN certificate is missing" in script
    assert "media CDN private key is missing" in script
