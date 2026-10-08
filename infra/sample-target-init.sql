-- Synthetic Indian PII for scanning demos (SRS 12.1 sample-target). Fabricated values;
-- the Aadhaar numbers are shaped like Aadhaar but are not validated here (the engine
-- applies the Verhoeff check at scan time). Nothing here is real personal data.
CREATE TABLE customers (
    id              serial PRIMARY KEY,
    full_name       text,
    email           text,
    mobile          varchar(15),
    aadhaar_number  char(14),
    pan_no          char(10),
    date_of_birth   date,
    address         text,
    gender          varchar(16)
);

INSERT INTO customers
    (full_name, email, mobile, aadhaar_number, pan_no, date_of_birth, address, gender)
VALUES
    ('Ananya Roy', 'ananya.roy@example.com', '9876543210', '2341 2341 2340',
     'ABCPK1234L', '1991-04-12', '12, MG Road, Bengaluru, 560001', 'female'),
    ('Rahul Verma', 'rahul.verma@example.com', '9123456780', '3675 9834 6789',
     'AAAPL1234C', '2010-08-01', '7, Park Street, Kolkata, 700016', 'male');

CREATE TABLE kyc_documents (
    id            serial PRIMARY KEY,
    customer_id   int,
    passport_no   varchar(12),
    voter_id      char(10),
    bank_account  varchar(18),
    ifsc_code     char(11)
);

INSERT INTO kyc_documents (customer_id, passport_no, voter_id, bank_account, ifsc_code)
VALUES (1, 'M1234567', 'ABC1234567', '123456789012', 'HDFC0001234');
