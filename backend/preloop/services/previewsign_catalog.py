"""Vendor-documented model capability, never individual-device trust.

Reviewed 2026-10-21. Firmware 5.8 YubiKey 5 Series identifiers joined to
its previewSign extension matrix. See workshop previewsign-vendor-catalog.md.
"""

CATALOG_VERSION = "2026-10-21"
AAGUID_SOURCE = "https://support.yubico.com/s/article/YubiKey-hardware-FIDO2-AAGUIDs"
CAPABILITY_SOURCE = "https://docs.yubico.com/hardware/yubikey/yk-tech-manual/yk5-apps-fido.html#supported-extensions"
PREVIEWSIGN_MODELS = {
    "f4ce5fc0-57d3-46f5-a736-efb7d5bc63b5": "YubiKey 5 NFC / 5C NFC",
    "41e39911-c669-4811-b860-c6ad0b411b96": "YubiKey 5 NFC / 5C NFC enterprise",
    "0ebd9f2c-f685-441c-8c3e-a02a234a840a": "YubiKey 5 NFC / 5C NFC Enhanced PIN",
    "9a3f2abd-a73d-439c-9ee7-1b53a857eaa7": "YubiKey 5 NFC / 5C NFC Enhanced PIN enterprise",
    "0a357157-9b18-4c8a-920e-d156e972b2f8": "YubiKey 5 Nano / 5C Nano / 5C",
    "524de2de-982f-49b4-a769-2b5e3b73ad79": "YubiKey 5 Nano / 5C Nano / 5C enterprise",
    "03012cb7-4fb2-42e7-9e8d-a81f10e2a5e9": "YubiKey 5Ci",
    "c3479970-e58a-4f70-836f-853bf42fb063": "YubiKey 5Ci enterprise",
    "eb7ef748-cbe0-4b40-b8f6-07bd2d592d35": "YubiKey 5 CCN NFC",
    "3ec9c8d3-a5a7-415b-a7b5-f1d606368d3f": "YubiKey 5 CCN NFC enterprise",
}
