"""KYC document types and required set (A-KYC — SPEC_AMENDMENTS §19)."""

# App config — not in DB because pujari_documents.doc_type is free-text VARCHAR(30).
REQUIRED_DOC_TYPES: tuple[str, ...] = ("identity_proof", "address_proof", "photo")

DOC_TYPE_LABELS: dict[str, str] = {
    "identity_proof": "Identity proof (Aadhaar / ID)",
    "address_proof": "Address proof",
    "photo": "Profile photo",
}
