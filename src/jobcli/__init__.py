"""JobCLI — production-grade CLI for automated job applications.

This top-level package is intentionally lightweight. The only side effect of
importing ``jobcli`` is the TLS bootstrap: we inject the OS-native trust
store into Python's ``ssl`` module so every downstream library (OpenAI,
Anthropic, Gemini, ``requests``, ``httpx``) authenticates HTTPS against the
same roots — including the corporate MITM roots that Windows users typically
have installed system-wide but **not** in Python's bundled ``certifi`` store.

See :mod:`jobcli.utils.tls` for the configuration knobs
(``JOBCLI_INSECURE_TLS``, ``JOBCLI_SSL_CA_BUNDLE``, ``JOBCLI_TLS_DEBUG``).
"""

from jobcli.utils.tls import configure_tls as _configure_tls

# Run once at first import. Idempotent — safe to call from multiple entry
# points. Must execute before any HTTP client (openai.OpenAI, httpx.Client,
# requests.Session, etc.) is built anywhere in the codebase.
_configure_tls()
