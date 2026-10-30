# Local security review

Reviewed controls include authenticated ownership checks for conversations,
documents, retrieval, indexing, and metrics; upload extension, MIME, size, and
archive-expansion limits; HTTP(S)-only citation URLs; React's escaped Markdown
rendering; prompt-injection boundaries; content-free metrics; validation-log
redaction; bounded research calls; bounded chat inputs; explicit CORS origins;
and per-user local request ceilings. Regression tests cover cross-user IDOR,
forged identifiers, refresh/access token type separation, unsafe URLs,
dangerous uploads, provider failure sanitization, retrieval/generation prompt
injection, and resource bounds.

Known limitations for local use:

- JWT logout is client-side deletion. Issued stateless access and refresh
  tokens are not server-revoked; token rotation/revocation needs durable token
  state and a future migration.
- Browser tokens are kept in `localStorage`, so a future same-origin XSS flaw
  could read them. The current React UI does not enable raw HTML, validates
  source URLs, and uses `noopener noreferrer`, but production deployment should
  consider secure HttpOnly cookies plus CSRF protection and a restrictive CSP.
- Request counters and usage telemetry are process-local. Multiple API workers
  would each have independent ceilings; production-grade enforcement needs a
  shared rate-limit store.
- Uploaded documents are parsed but not malware-scanned or sandboxed. Only
  trusted local users should upload files until isolated parsing and scanning
  are introduced.
- The allowlist defaults are for Vite development origins. Any deployed origin
  must be explicitly configured; TLS and reverse-proxy security are outside
  this local project.
- Gemini and Tavily receive the minimum text required by their workflows.
  Provider retention and regional-compliance settings must be reviewed before
  processing sensitive documents.

No penetration test, dependency vulnerability scan, production threat model,
or real-provider adversarial evaluation is claimed.
