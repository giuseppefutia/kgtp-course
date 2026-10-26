#!/usr/bin/env python3
"""Calibration check for the PII filter in extract_contracts.py.

    python tools/04-building-the-graph/test_pii_filter.py

Every fixture below is SYNTHETIC — invented for this test, not copied from any
real contract. Names, addresses, phone numbers and mailboxes are fabricated.
Nothing here is extracted from the corpus, precisely because a test file
carrying real personal data would defeat the filter it is testing.

The fixtures encode the policy: inclusion by role, not by public availability.
The three KEEP cases are pages dense with business contact details, which a
naive "does this page contain an address" rule would wrongly discard. The DROP
cases are directories of individuals.

Thresholds are provisional until the filter runs against the real Howard Brown
document (PO C029840), whose board directory is the acceptance test.
"""

from __future__ import annotations

import sys
from pathlib import Path

from corpus.extract_contracts import pii_score, pii_signals

THRESHOLD = 3

KEEP = {
    "signature page, one business contact": """
        IN WITNESS WHEREOF, the parties have executed this Agreement.
        NORTHSIDE PAVING & INFRASTRUCTURE LLC
        4400 W Fictional Ave, Chicago, IL 60600
        Telephone: (312) 555-0100
        By: J. Sample, Vice President
        Email: contracts@northsidepaving.example
        Department of Transportation, City of Chicago
        By: A. Placeholder, Commissioner
    """,
    "notices clause, three business addresses": """
        SECTION 12. NOTICES. All notices shall be in writing and delivered to:
        If to the City: Department of Finance, 121 N Invented St, Chicago, IL
        If to the Contractor: 900 S Imaginary Blvd, Chicago, IL 60601
        With a copy to: Corporation Counsel, 30 N Notreal Plaza, Chicago, IL
        Telephone (312) 555-0111. Facsimile (312) 555-0112.
    """,
    "insurance certificate": """
        CERTIFICATE OF LIABILITY INSURANCE
        PRODUCER: Example Risk Brokers, 200 W Madeup Rd, Naperville, IL 60540
        Phone (630) 555-0130  Fax (630) 555-0131
        INSURED: Northside Paving LLC, 4400 W Fictional Ave, Chicago IL 60600
        INSURER A: Placeholder Casualty Company, 1 Invented Way, Hartford CT
        General Liability, Automobile Liability, Umbrella Excess, Workers Comp.
    """,
    "single personal mailbox, nothing else": """
        Correspondence regarding this solicitation may be directed to the
        authorised representative at samplebidder1979@gmail.com during the
        question period, which closes on the date stated in the invitation.
    """,
}

DROP = {
    "board of directors directory": """
        BOARD OF DIRECTORS - CONTACT LIST
        Chair: Sample Person One, 1420 W Invented St Apt 3R, Chicago IL 60622
          home (773) 555-0140  cell (773) 555-0141  personone@gmail.com
        Vice Chair: Sample Person Two, 5533 N Notreal Ave Unit 2, Chicago IL
          home (773) 555-0142  persontwo@yahoo.com
        Treasurer: Sample Person Three, righthere 812 E Madeup Dr, Oak Park IL
          home (708) 555-0143  cell (708) 555-0144  p3@hotmail.com
        Secretary: Sample Person Four, 77 S Fictional Ct, Evanston IL 60201
          home (847) 555-0145  personfour@aol.com
        Member: Sample Person Five, 3311 W Pretend Blvd Apt 12, Chicago IL
          home (312) 555-0146  cell (312) 555-0147
    """,
    "staff roster with home contacts": """
        PROGRAM STAFF - EMERGENCY CONTACT ROSTER
        Case Manager, residence 2200 N Invented Ave Apt 5, cell (312) 555-0150
        Outreach Worker, residence 1815 S Notreal St Unit B, cell (312) 555-0151
        Counsellor, residence 640 W Madeup Ln, home phone (773) 555-0152
        Nurse, residence 4501 N Fictional Rd Apt 9, cell (773) 555-0153
        Driver, residence 118 E Pretend Way, home phone (708) 555-0154
    """,
}


def main() -> int:
    failures = 0
    for expect_drop, cases in ((False, KEEP), (True, DROP)):
        want = "DROP" if expect_drop else "KEEP"
        for label, text in cases.items():
            signals = pii_signals(text)
            score, reasons = pii_score(signals)
            dropped = score >= THRESHOLD
            ok = dropped == expect_drop
            failures += not ok
            got = "DROP" if dropped else "KEEP"
            print(f"[{'ok ' if ok else 'FAIL'}] want {want} got {got} "
                  f"score={score}  {label}")
            print(f"         signals={signals}")
            if reasons:
                print(f"         reasons={reasons}")

    print()
    if failures:
        print(f"{failures} fixture(s) misclassified — recalibrate before "
              f"running against real documents.")
        return 1
    print("All fixtures classified as intended.")
    print("NOTE: synthetic only. The acceptance test is the board directory in "
          "PO C029840 (Howard Brown), which must fall out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
