# Provider rejections and Seedream references

Seedream edits use provider-hosted references. Local uploads must still exist;
external references are downloaded with a byte limit, public-address validation
and redirects disabled, checked as JPEG/PNG/WebP, and uploaded to KIE file
storage before a generation task is submitted. Missing, unreachable, redirected
or invalid media must be uploaded again. The adapter never submits a task with
the original external URL after staging fails.

Site, Mini App, realtime events and Telegram notices share safe explanations for
the verified copyright, missing-image and `provider_rejected_request` failures.
Hidden recipes remain private: only fixed explanations are returned, while raw
provider diagnostics stay in the generation record. Existing guarded refunds
remain responsible for balance settlement; an error message alone never proves
that a refund happened.

A terminal Seedance rejection marked `retryable=false` is not automatically
resubmitted or sent to another provider. The observed provider response gives no
more specific cause. Users should check their description and references before
a new attempt. A confirmed Seedream copyright rejection requires revised input
that the user has rights to use; it is not treated as a transport outage.

These changes cannot recover an expired original image or guarantee acceptance
by provider moderation. No provider routes, tariffs, schema, credentials or
admin configuration change.
