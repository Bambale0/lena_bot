# Video-to-prompt transport limits

The existing product limit is **100 MiB per file** for `/api/v1/video-prompt`
and `/api/web/video-prompt`. The shared Mini App handler validates both routes.
The active TypeScript client rejects oversized files before uploading them.
The text Telegram bot keeps its existing **20 MiB** Bot API download constraint;
it uses the same provider deadline and existing refund/cleanup handling.

## Checked-in ingress

`docker-compose.yml` mounts `nginx.conf` as the canonical Nginx configuration.
The production deploy script starts this Compose service. Both application host
blocks (`apixbotai.com` and `testapi.chillcreative.ru apix.chillcreative.ru`) have
exact locations for the two video-prompt routes:

- `client_max_body_size 101M`: the existing 100 MiB file cap plus up to 1 MiB of
  multipart overhead. This is a complete HTTP-body envelope, not an increased
  application file limit
- `proxy_read_timeout 240s`: bounded extra time for the synchronous analysis
- The same upstream and forwarding headers as the existing application proxy

The general **35M / 120s** settings, websocket locations, other hosts and retired
V4 client remain unchanged. `deploy/nginx-*.conf` are separate templates and are
not mounted by canonical Compose. Any deployment using them needs its own
configuration review; changing this file alone does not prove live settings.

## Deadline and resource semantics

The provider call has an overall **180-second asyncio deadline**, in addition to
HTTPX's per-operation timeout. No automatic paid retry is added. Expiration becomes
a typed provider failure so existing site/Mini App/bot handlers refund once and
delete their temporary public file. The timeout wraps provider IO, not the whole
paid handler, so its own cancellation does not bypass refund handling.

The proxy leaves a 60-second margin beyond that provider budget, but its timer is
an inactivity timer, not an end-to-end request deadline. Upload parsing, DB work,
temporary storage and cleanup also take time; their worst-case duration is not
bounded by the provider deadline. The active client does not introduce a shorter
abort timer. A larger upload, slow DB, outer proxy or disconnected client can still
fail independently; this is not a resumable job or durable result-recovery flow.

The API reads at most `MAX_VIDEO_PROMPT_BYTES + 1` bytes into its validation buffer,
including oversized-file rejection. FastAPI/Starlette has already parsed and
spooled multipart content before entering the route. Therefore this limits the
route's heap copy, not the parser's total memory or temporary-disk usage. The 101M
body envelope bounds each request only when it traverses the canonical ingress;
direct backend access, concurrent uploads and parser field/file limits need
separate capacity/security controls. No global upload limit is raised.

## Verification and rollout

- Service tests exercise deadline cancellation without real-time waiting or a
  live provider; cross-surface tests check once-only spend/refund and cleanup
- Upload tests exercise exact-cap acceptance and one-byte-over rejection before
  billing/provider/storage, with a scaled fixture and a bounded read assertion
- Nginx structural contract tests check exact routes, body/timeout values,
  unchanged generic limits and forwarding headers
- CI pre-pulls the official `nginx:alpine` image matching Compose, then runs actual
  `nginx -t` on byte-identical full `nginx.conf` and `nginx-media.conf` copies with
  throwaway TLS certificates and loopback upstream aliases. The container has no
  network or published ports. An intentional invalid-route directive must fail,
  proving that the mounted config is checked. Explicit CI enablement fails on
  missing Docker/image; local Docker cases are skipped and not reported as passed
- Client unit tests exercise the actual API class and pre-upload rejection

Before rollout, validate the effective Nginx configuration and any outer proxies,
run Nginx syntax validation, and use synthetic/mocked upstreams for multipart and
slow-response smoke tests. No production configuration, reload or paid request
was used to establish this checked-in fix. The original incident's production
root cause remains unverified.

Sources: [Nginx body-size directive](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size),
[Nginx response timeout](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout),
[HTTPX timeout semantics](https://www.python-httpx.org/advanced/timeouts/).
