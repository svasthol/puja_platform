"""KYC document types and required set (A-KYC — SPEC_AMENDMENTS §19)."""

# App config — not in DB because pujari_documents.doc_type is free-text VARCHAR(30).
REQUIRED_DOC_TYPES: tuple[str, ...] = ("identity_proof", "address_proof", "photo")

DOC_TYPE_LABELS: dict[str, str] = {
    "identity_proof": "Identity proof (Aadhaar / ID)",
    "address_proof": "Address proof",
    "photo": "Profile photo",
}

# DigiLocker scope → document types ingested from vendor (photo is camera selfie only).
SCOPE_TO_DOC_TYPES: dict[str, tuple[str, ...]] = {
    "ADHAR": ("identity_proof", "address_proof"),
}

KYC_CONSENT_PURPOSE_DIGILOCKER_AADHAAR = "digilocker_aadhaar"
KYC_CONSENT_TEXT_VERSION = "v1"
KYC_CONSENT_TEXT = (
    "I consent to Mana Guruji fetching my Aadhaar details from DigiLocker "
    "for partner KYC verification under applicable Indian law."
)
