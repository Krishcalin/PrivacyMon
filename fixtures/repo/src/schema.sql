-- Sample migration for the Git connector fixture (synthetic).
-- Column names and comments carry PII context the detectors use.

CREATE TABLE customers (
    id              BIGSERIAL PRIMARY KEY,
    full_name       TEXT        NOT NULL,     -- person name
    email           TEXT,                     -- contact email
    mobile          VARCHAR(15),              -- Indian mobile
    aadhaar_number  CHAR(12),                 -- Aadhaar (critical)
    pan_no          CHAR(10),                 -- PAN
    date_of_birth   DATE,                     -- DOB
    address         TEXT,                     -- postal address
    gender          VARCHAR(16),
    photo           BYTEA,                    -- scanned ID / photograph
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE kyc_documents (
    id              BIGSERIAL PRIMARY KEY,
    customer_id     BIGINT REFERENCES customers(id),
    passport_no     VARCHAR(12),
    voter_id        CHAR(10),
    bank_account    VARCHAR(18),
    ifsc_code       CHAR(11),
    fingerprint     BYTEA                     -- biometric template (critical)
);
