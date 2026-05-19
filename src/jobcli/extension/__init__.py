"""TalentScreen extension loading and Playwright autofill bridge."""

from jobcli.extension.autofill_bridge import (
    ExtensionAutofillOptions,
    ExtensionAutofillResult,
    extension_api_available,
    export_extension_report,
    find_autofill_frame,
    run_extension_autofill,
    wait_for_autofill_api,
)
from jobcli.extension.helpers import (
    ATS_HOST_FRAGMENTS,
    chromium_extension_launch_args,
    extension_manifest_has_page_bridge,
    is_likely_ats_frame_url,
    read_extension_manifest_version,
    resolve_extension_dir,
    verify_extension_in_browser,
)
from jobcli.extension.install import (
    extension_install_dir,
    install_bundled_extension,
    is_valid_extension_dir,
    refresh_installed_extension,
)

__all__ = [
    "ATS_HOST_FRAGMENTS",
    "ExtensionAutofillOptions",
    "ExtensionAutofillResult",
    "chromium_extension_launch_args",
    "extension_api_available",
    "extension_install_dir",
    "extension_manifest_has_page_bridge",
    "export_extension_report",
    "find_autofill_frame",
    "install_bundled_extension",
    "is_likely_ats_frame_url",
    "is_valid_extension_dir",
    "refresh_installed_extension",
    "read_extension_manifest_version",
    "resolve_extension_dir",
    "run_extension_autofill",
    "verify_extension_in_browser",
    "wait_for_autofill_api",
]
