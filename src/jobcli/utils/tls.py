"""Centralized TLS configuration for every outbound HTTPS call JobCLI makes.

Why this exists
---------------
Many users (especially on Windows + corporate networks) see errors like::

    SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer certificate

Two common root causes:

1. **Corporate MITM proxy / AV** (Zscaler, Netskope, Bitdefender, Kaspersky,
   Cisco Umbrella, …) silently re-signs HTTPS with a private root CA that is
   installed in the *OS* trust store but **not** in Python's bundled
   ``certifi`` store.
2. The user's Python install has a stale or broken ``certifi`` bundle.

The fix is to make Python's ``ssl`` module read trust roots from the **OS
native store**. The third-party ``truststore`` package does exactly that, and
the Python core team has effectively endorsed it (PEP 599 conversation,
``pip`` ships with it baked-in).

Behavior
--------
``configure_tls()`` is idempotent and runs once at CLI startup. It picks the
best strategy in this order:

1. ``JOBCLI_INSECURE_TLS=1`` → leave verification off everywhere (callers must
   pass ``verify=False`` themselves). **Insecure**, last resort.
2. ``JOBCLI_SSL_CA_BUNDLE=<path-to.pem>`` → set ``SSL_CERT_FILE`` /
   ``REQUESTS_CA_BUNDLE`` so every library (``ssl``, ``requests``, ``httpx``,
   ``openai``, ``anthropic``, ``google-genai``) honors that PEM.
3. **Default** → ``truststore.inject_into_ssl()`` so ``ssl`` reads the OS
   native trust store (Windows cert store, macOS Keychain, Linux roots).
   No env vars required — this is what fixes 99% of "Connection error."
   reports out of the box.

All callers should use :func:`requests_verify` and :func:`httpx_verify` when
building their HTTP clients so the choice is consistent. Loud-print is OFF by
default — pass ``verbose=True`` (or set ``JOBCLI_TLS_DEBUG=1``) when you want
to see what strategy was selected.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Sentinels populated by ``configure_tls()`` and read by ``*_verify()``.
_configured: bool = False
_strategy: str = "default"  # "insecure" | "ca-bundle" | "truststore" | "certifi" | "default"
_ca_bundle_path: Optional[str] = None
_insecure: bool = False


def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def configure_tls(verbose: bool = False) -> str:
    """Configure process-wide TLS trust. Idempotent. Returns the strategy name.

    Call this **once**, as early as possible — ideally before any HTTPS client
    is constructed. ``jobcli.cli.main`` calls it at module-import time.
    """
    global _configured, _strategy, _ca_bundle_path, _insecure

    if _configured:
        return _strategy

    debug = verbose or _is_truthy(os.getenv("JOBCLI_TLS_DEBUG"))

    if _is_truthy(os.getenv("JOBCLI_INSECURE_TLS")):
        _insecure = True
        _strategy = "insecure"
        _configured = True
        if debug:
            logger.warning(
                "TLS verification disabled via JOBCLI_INSECURE_TLS — your connection "
                "is no longer authenticated. Prefer JOBCLI_SSL_CA_BUNDLE in production."
            )
        return _strategy

    ca = (os.getenv("JOBCLI_SSL_CA_BUNDLE") or "").strip()
    if ca and os.path.isfile(ca):
        _ca_bundle_path = ca
        # Make sure every library that respects these env vars (urllib3,
        # requests, httpx, openai, anthropic, google-genai) picks it up too.
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
        os.environ.setdefault("CURL_CA_BUNDLE", ca)
        _strategy = "ca-bundle"
        _configured = True
        if debug:
            logger.info("TLS using JOBCLI_SSL_CA_BUNDLE=%s", ca)
        return _strategy

    # Preferred path on Python 3.10+: bridge ssl to the OS trust store. This
    # transparently picks up corporate roots installed in the Windows cert
    # store / macOS Keychain / Linux trust dirs.
    if sys.version_info >= (3, 10):
        try:
            import truststore  # type: ignore[import-not-found]

            truststore.inject_into_ssl()
            _strategy = "truststore"
            _configured = True
            if debug:
                logger.info("TLS using OS-native trust store via truststore.")
            return _strategy
        except ImportError:
            if debug:
                logger.info(
                    "truststore not installed; falling back to certifi. "
                    "Run 'pip install truststore' for OS-native trust support."
                )
        except Exception as exc:  # pragma: no cover - defensive
            if debug:
                logger.warning("truststore inject failed: %s — falling back.", exc)

    # Last resort: explicit certifi bundle. Same as default behavior of most
    # libraries, surfaced so that overrides are visible.
    try:
        import certifi

        bundle = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
        _ca_bundle_path = bundle
        _strategy = "certifi"
        _configured = True
        if debug:
            logger.info("TLS using certifi bundle at %s", bundle)
        return _strategy
    except ImportError:
        pass

    _strategy = "default"
    _configured = True
    return _strategy


def is_insecure() -> bool:
    """Returns True iff ``JOBCLI_INSECURE_TLS`` was honored."""
    configure_tls()
    return _insecure


def ca_bundle_path() -> Optional[str]:
    """Returns the explicit CA bundle path if one was configured, else ``None``."""
    configure_tls()
    return _ca_bundle_path


def strategy() -> str:
    """Returns the strategy name picked by :func:`configure_tls`."""
    configure_tls()
    return _strategy


def requests_verify() -> Any:
    """Value to pass to ``requests.*(verify=...)``.

    Returns one of:
        - ``False`` when ``JOBCLI_INSECURE_TLS=1``;
        - a path to a PEM file when ``JOBCLI_SSL_CA_BUNDLE`` is set;
        - ``True`` otherwise (use the system / truststore-injected default).
    """
    configure_tls()
    if _insecure:
        return False
    if _ca_bundle_path:
        return _ca_bundle_path
    return True


def httpx_verify() -> Any:
    """Value to pass to ``httpx.Client(verify=...)``.

    Same semantics as :func:`requests_verify`. When the truststore strategy is
    active, returning ``True`` is correct: ``httpx`` builds an
    ``ssl.SSLContext`` via ``ssl.create_default_context()`` which truststore
    has already monkey-patched to read the OS trust store.
    """
    return requests_verify()
