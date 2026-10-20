# Provider rejections and Seedream references

Seedream edits use provider-hosted references. Local uploads must still exist;
local Seedream images are decoded as JPEG/PNG/WebP before stream upload.
External references use the documented KIE URL Upload API: APIX never opens
the supplied URL, avoiding server-side DNS rebinding/SSRF. The adapter requires
a successful upload with image MIME metadata, a positive size of at most 30 MiB
and an HTTPS download URL before a generation task is submitted. Missing,
unreachable or invalid media must be uploaded again. The adapter never submits a task with the original external URL after staging
fails. File staging is free according to the [KIE upload documentation](https://docs.kie.ai/file-upload-api/quickstart); the [URL upload contract](https://docs.kie.ai/file-upload-api/upload-file-url) specifies request fields and response metadata.

Site, Mini App, realtime events and Telegram notices share safe explanations for
the verified copyright, missing-image and `provider_rejected_request` failures.
Hidden recipes remain private: only fixed explanations are returned, while raw
provider diagnostics stay in the generation record. Existing guarded refunds
remain responsible for balance settlement; new reference admission failures
use one atomic failed-status/wallet/ledger transition across site and Mini App; an error message alone never proves
that a refund happened.

A terminal Seedance rejection marked `retryable=false` is not automatically
resubmitted or sent to another provider. The observed provider response gives no
more specific cause. Users should check their description and references before
a new attempt. A confirmed Seedream copyright rejection requires revised input
that the user has rights to use; it is not treated as a transport outage.

These changes cannot recover an expired original image or guarantee acceptance
by provider moderation. No provider routes, tariffs, schema, credentials or
admin configuration change.
