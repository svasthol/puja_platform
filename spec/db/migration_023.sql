-- Migration 023 — Partner KYC selfie presign intermediate status.
-- Chains after 022. Idempotent.
-- `uploading` = presigned PUT issued, object not yet confirmed; excluded from admin pending queue.

DO $$
DECLARE
    def text;
BEGIN
    SELECT pg_get_constraintdef(c.oid) INTO def
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'pujari_documents'
      AND c.conname = 'pujari_documents_status_check';

    IF def IS NOT NULL AND def LIKE '%uploading%' THEN
        RAISE NOTICE 'migration_023: pujari_documents status already includes uploading';
        RETURN;
    END IF;

    ALTER TABLE pujari_documents DROP CONSTRAINT IF EXISTS pujari_documents_status_check;
    ALTER TABLE pujari_documents
        ADD CONSTRAINT pujari_documents_status_check
        CHECK (status IN ('pending', 'verified', 'rejected', 'uploading'));
END $$;
