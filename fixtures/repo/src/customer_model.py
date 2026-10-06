"""Sample application source for the Git connector fixture.

Synthetic only. The Git connector parses identifiers (field, column, variable
names) and string literals; this file exercises both. All values are fabricated.
"""


class Customer:
    """A customer record with personal-data fields the detectors should flag."""

    def __init__(self):
        self.full_name = ""        # person name
        self.email = ""            # email
        self.mobile = ""           # mobile
        self.aadhaar_number = ""   # Aadhaar
        self.pan_no = ""           # PAN
        self.date_of_birth = ""    # DOB
        self.address = ""          # address
        self.gender = ""           # gender

    # String literals carrying example values (fabricated).
    SAMPLE = {
        "email": "ananya.roy@example.com",
        "aadhaar_number": "2341 2341 2340",
        "pan_no": "ABCPK1234L",
    }
