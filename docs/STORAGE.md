# File storage

Voice notes, photos and PDFs go through `services/storage_service.py`. Locally they sit in
`uploads/` and `outputs/`. On Railway the app's disk is wiped on every redeploy, so the hosted
app must use a storage bucket (`STORAGE_BACKEND=s3`).

## Railway storage bucket (what the hosted app uses)

1. In the Railway project, add a **Storage Bucket**.
2. In the bucket's **Credentials** tab, copy the values into the app service's **Variables**:

| Variable | From Credentials |
|---|---|
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET` | the bucket name (display name plus a short hash) |
| `S3_ENDPOINT_URL` | the endpoint, e.g. `https://t3.storageapi.dev` |
| `S3_REGION` | the region, e.g. `auto` |
| `S3_ACCESS_KEY_ID` | the access key id |
| `S3_SECRET_ACCESS_KEY` | the secret access key |
| `S3_ADDRESSING_STYLE` | `virtual` for new buckets; `path` if the tab says path-style |

   Railway's own names from the bucket's Variables (`BUCKET`, `ENDPOINT`, `REGION`, `ACCESS_KEY_ID`,
   `SECRET_ACCESS_KEY`) work too; an `S3_*` variable wins if both are set.
3. Redeploy. `/healthz` reports `"storage": "s3", "bucket_set": true`. In the app service's shell,
   `python3 scripts/check_storage.py` writes, reads back, links and deletes a test file.

The bucket is private: the app checks who may see a file, then redirects to a link that works for
`S3_SIGNED_URL_SECONDS` (15 minutes). Storage costs $0.015 per GB a month; downloads and requests
are free.

Cloudflare R2 or AWS S3 work the same way with their own endpoint and keys.

## Before go-live (parked by Saksham on 2026-10-27, until after the beta)

Printed QR codes must keep playing for good. Before launch, decide on:

- a domain owned for 10+ years on auto-renew, set as `PUBLIC_BASE_URL` before any real book is printed;
- moving revealed books to a cheaper rarely-read class (R2 Infrequent Access, still instant);
- a nightly second copy of every file with another provider;
- "download all voice notes" for the family;
- keeping only the newest PDFs, and recording in the app at 32 kbps.
