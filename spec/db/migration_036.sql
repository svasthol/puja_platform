-- Migration 036 — Customer trust card (Slice B): published profile photo pointer.
-- Chains after 035. Admin sets this when the current `photo` KYC doc is verified.

ALTER TABLE pujaris
    ADD COLUMN IF NOT EXISTS customer_profile_photo_doc_id UUID
        REFERENCES pujari_documents(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_pujaris_customer_profile_photo_doc
    ON pujaris (customer_profile_photo_doc_id)
    WHERE customer_profile_photo_doc_id IS NOT NULL;
