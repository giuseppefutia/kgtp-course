#!/usr/bin/env python3
"""Read the fixed-layout forms in the corpus without a model.

Instructor-only. Runs after `extract_contracts.py`, over the extracted text.

    python tools/04-building-the-graph/corpus/parse_forms.py data/chicago/2022-2026
    python tools/04-building-the-graph/corpus/parse_forms.py data/chicago/2022-2026 --form eds_certificate

Writes one JSONL per form under `<dir>/forms/`, and prints what each field
yielded so a drop in a field is visible rather than silent.

=============================================================================
WHY THESE PAGES DO NOT GO TO THE MODEL -- measured 2026-10-19
=============================================================================
Four of the page types in this corpus are the same form filled in again and
again, with constant field labels. Over the 2022-2026 corpus a label-based
reader finds, per page: the EDS certificate's eight fields on 96-99% of 4,149
pages, the contract summary's identity fields on 93-99% of 735, the
modification summary's on 97-98% of 2,268.

What it does not find is mostly not there. The contract summary's dates are
missing on the 24% of pages that say "Term of Contract is not applicable"; the
modification summary carries an amount on 29% because a pure time extension has
none. A model asked for those slots returns null too, five hours of GPU later.

So these pages are read here: exactly, at no cost, and -- the reason that
decides it -- reproducibly. A parser pinned in the repository gives twenty
students the same rows, which a served model does not (see CLAUDE.md on why
every version in this project is exact).

The model's turn is `extract_typed.py`, on the pages whose layout is free.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path


def read_labelled(text: str, labels: list[str]) -> dict[str, str | None]:
    """Each field is the text between its label and the next label present.

    Not a per-field regex: a value in these forms often runs over two or three
    lines (`City Department:` then `DEPARTMENT OF FAMILY AND SUPPORT` then
    `SERVICES`), and a line-anchored pattern silently truncates it to the first
    line. Taking the span up to the next label that actually appears keeps the
    whole value and tolerates a missing label in the middle.
    """
    found = []
    for lab in labels:
        m = re.search(re.escape(lab) + r"\s*:?", text, re.I)
        if m:
            found.append((m.end(), lab))
    found.sort()
    out: dict[str, str | None] = {lab: None for lab in labels}
    for i, (end, lab) in enumerate(found):
        stop = found[i + 1][0] - len(found[i + 1][1]) - 1 if i + 1 < len(found) else len(text)
        val = " ".join(text[end:stop].split())
        out[lab] = val or None
    return out


# Identifier fields hold one token. The span reader cannot know that, and where
# a label is the last one on the page -- `Contract #` on the EDS certificate --
# the span runs on into the prose that follows and the value comes out as
# "100721 The Economic Disclosure Statement referenced above...". Measured
# 21/10/2026: that alone made 3,931 of 4,365 EDS certificates look as if their
# contract number disagreed with the record, when none of them did.
IDENT = re.compile(r"^[A-Za-z]?[\d][\w.-]*")


def first_token(v: str | None) -> str | None:
    """The leading identifier of a span, or None if it does not start with one."""
    if not v:
        return None
    m = IDENT.match(v.strip())
    return m.group(0) if m else v.split()[0] if v.split() else None


MONEY = re.compile(r"\$\s?([\d,]+\.\d{2})")
# A modification page lists its requests as: number, reason in capitals, prose.
MOD_REQ = re.compile(r"^(\d{6})\s+([A-Z][A-Z &/]{3,})\s*$", re.M)


def eds_certificate(text: str) -> dict:
    # The last labels on the page are followed by two paragraphs of standing
    # text, so the terminators belong in the list too: without them `Title` and
    # `Contract #` swallow the prose. Measured 21/10/2026.
    f = read_labelled(text, ["EDS Number", "Certificate Printed on", "Date of This Filing",
                             "Original Filing Date", "Disclosing Party", "Filed by", "Title",
                             "Matter", "Applicant", "Specification #", "Contract #",
                             "The Economic Disclosure Statement", "A copy of the EDS",
                             "Docusign Envelope", "DocuSign Envelope"])
    return {
        "eds_number": first_token(f["EDS Number"]),
        "printed_on": f["Certificate Printed on"],
        "filed_on": f["Date of This Filing"],
        "disclosing_party": f["Disclosing Party"],
        "filed_by": f["Filed by"],
        "filer_title": f["Title"],
        "matter": f["Matter"],
        "applicant": f["Applicant"],
        "spec_in_text": first_token(f["Specification #"]),
        "contract_in_text": first_token(f["Contract #"]),
    }


def contract_summary(text: str) -> dict:
    # Every label on the form has to be in this list, including the ones whose
    # value we do not want: a label that is missing does not drop a field, it
    # lets the previous field's span run through it. Measured 21/10/2026, the
    # four labels missing from the first version contaminated `title` on 90.6%
    # of the pages, `end_date` on 70.9% and `contract_area` on 77.6%.
    f = read_labelled(text, ["Contract (PO) Number", "Contract Purchase Order Number",
                             "Specification Number", "Name of Contractor", "Vendor Name",
                             "Vendor Number / Vendor Site", "Vendor Number",
                             "City Department", "Title of Contract", "Term of Contract",
                             "Start Date", "End Date", "Dollar Amount of Contract",
                             "Maximum Compensation", "Brief Description of Work",
                             "Procurement Services Contract Area", "Contract Type",
                             "Please refer", "Submission Date"])
    amounts = MONEY.findall(text)

    def money_in(*spans: str | None) -> str | None:
        """The form writes the amount after a parenthetical that varies; anchor
        on the figure inside the span, not on the span itself."""
        for sp in spans:
            m = MONEY.search(sp or "")
            if m:
                return f"${m.group(1)}"
        return None
    return {
        "po_in_text": first_token(f["Contract (PO) Number"] or f["Contract Purchase Order Number"]),
        "spec_in_text": first_token(f["Specification Number"]),
        "vendor_in_text": f["Name of Contractor"] or f["Vendor Name"],
        "department_in_text": f["City Department"],
        "title": f["Title of Contract"],
        "amount": money_in(f["Maximum Compensation"], f["Dollar Amount of Contract"])
                  or (f"${amounts[0]}" if amounts else None),
        "start_date": f["Start Date"],
        "end_date": f["End Date"],
        "contract_area": f["Procurement Services Contract Area"],
        "contract_type": f["Contract Type"],
        "vendor_number": first_token(f["Vendor Number / Vendor Site"] or f["Vendor Number"]),
        "submission_date": f["Submission Date"],
    }


LABELS_THEN_VALUES = re.compile(r"Contract \(PO\) Number:\s*\n(?:[^\n]*:\s*\n){0,6}")
PAIRED = ["po_in_text", "revision", "spec_in_text", "vendor_in_text", "department_in_text"]


def recover_scrambled(text: str, doc_id: str) -> dict:
    """The layout that prints all the labels first and all the values after.

    Measured 19/10/2026: 420 of the 2,268 modification summaries come out of
    `pdftotext -raw` this way, and a label-anchored read correctly refuses them
    -- the span after `Contract (PO) Number:` is the next label, not a value.
    Pairing by position recovers 395 of them, but only under a guard: the first
    value must be the purchase order number the filename already declares. The
    25 that fail the guard stay null.

    The guard costs something that has to be said out loud. On these rows the
    purchase order in the text is no longer independent evidence about the
    record -- it was used to accept the pairing. They carry
    `_layout: "labels_then_values"` so a text-against-record comparison can
    leave them out.
    """
    m = LABELS_THEN_VALUES.search(text)
    if not m:
        return {}
    values = [x.strip() for x in text[m.end():].split("\n") if x.strip()]
    if not values or values[0] != doc_id.split("_r")[0]:
        return {}
    out = dict(zip(PAIRED, values[:len(PAIRED)]))
    out["_layout"] = "labels_then_values"
    return out


def modification_summary(text: str, doc_id: str = "") -> dict:
    f = read_labelled(text, ["Contract (PO) Number", "Modification Revision Number",
                             "Specification Number", "Name of Contractor", "City Department",
                             "Title of Contract", "Term of Contract", "Start Date", "End Date",
                             "Procurement Services Contact Person", "Please refer",
                             "It has been determined", "Vendor Number", "Submission Date",
                             "Mod Req Number"])
    reqs = [{"number": n, "reason": " ".join(r.split())} for n, r in MOD_REQ.findall(text)]
    row = {
        "po_in_text": first_token(f["Contract (PO) Number"]),
        "revision": first_token(f["Modification Revision Number"]),
        "spec_in_text": f["Specification Number"],
        "vendor_in_text": f["Name of Contractor"],
        "department_in_text": f["City Department"],
        "title": f["Title of Contract"],
        "start_date": f["Start Date"],
        "end_date": f["End Date"],
        "contact_person": f["Procurement Services Contact Person"],
        "vendor_number": first_token(f["Vendor Number"]),
        "submission_date": f["Submission Date"],
        "requests": reqs,
        "amounts_on_page": [f"${a}" for a in MONEY.findall(text)],
    }
    if not row["po_in_text"] and doc_id:
        row.update(recover_scrambled(text, doc_id))
    return row


def cdot_modification(text: str) -> dict:
    """The CDOT modification request, the only page that states cumulative totals.

    Its numbers are the running account of a contract: award, everything granted
    before, this request, and the new total -- plus the extension days summed to
    date. Measured 19/10/2026: 82 pages in the window carry it.
    """
    def after(label: str) -> str | None:
        m = re.search(re.escape(label) + r"[^\$\n]*\$?\s*([\d,]+\.\d{2})", text, re.I)
        return f"${m.group(1)}" if m else None
    days = re.search(r"Time Extension Approved To Date\.?\s*(\d+)", text, re.I)
    days_this = re.search(r"Time Extension in This Request\.?\s*(\d+)", text, re.I)
    proj = re.search(r"Project No\.?\s*([A-Z0-9-]+)", text)
    orig = re.search(r"Original Contract Completion Date\s*([\d\-A-Za-z]+)", text, re.I)
    adj = re.search(r"Adjusted Completion Date\.?\s*([\d\-A-Za-z]+)", text, re.I)
    cm = re.search(r"CM #:?\s*(\d+)", text)
    return {
        "project_no": proj.group(1) if proj else None,
        "cm_number": cm.group(1) if cm else None,
        "award": after("Amount of Contract Award"),
        "previous_line_items": after("LINE ITEM CHANGE REQUESTS PREVIOUS"),
        "previous_modifications": after("CONT. MODIFICATION REQUESTS PREVIOUS"),
        "this_request": after("Amount of This Modification Request"),
        "days_extension_to_date": days.group(1) if days else None,
        "days_extension_this_request": days_this.group(1) if days_this else None,
        "original_completion": orig.group(1) if orig else None,
        "adjusted_completion": adj.group(1) if adj else None,
        "amounts_on_page": [f"${a}" for a in MONEY.findall(text)],
    }


# ---------------------------------------------------------------------------
# The city's own people. Not a labelled form: four places where a page names a
# city employee in a fixed position, measured 21/10/2026 over the census.
#
#   the mailbox          nome.cognome@cityofchicago.org   248 people, 1,823 pages
#   the blanket PO       "BUYER:" then number, name, phone  15 people,   871
#   the CPO signature    the name on the line above the title 50 matches,  861
#   the commissioner     the name above "Commissioner of X"
#
# The reason this is worth its own extractor: the contracts CSV names no person
# at all on the city side, and these pages say who bought, who signed and who
# authorised -- each tied to a document that belongs to a dated revision.
#
# The filter matters more than the patterns. A signature block prints labels in
# the same shape as names, so `Comptroller Date` arrives 234 times looking like
# a person. The test that works is not a rule about the string: it is whether
# the name resolves against the employee dataset, which is why this extractor
# only collects and never decides.
# ---------------------------------------------------------------------------

CITY_EMAIL = re.compile(r"\b([a-z][\w\-]{1,20})\.([a-z][\w\-]{1,25})@cityofchicago\.org", re.I)
BUYER_LINE = re.compile(r"^BUYER:.*?\n\s*(\d{6})\s+([A-Z][A-Z .'\-]{4,40}?)\s+(\d{3}-\d{3}-\d{4})", re.M | re.S)
CPO_SIGN = re.compile(r"\n([A-Z][a-zA-Z.'\- ]{5,40})\n\s*Chief Procurement Officer", re.M)
COMMISSIONER = re.compile(r"\n([A-Z][a-zA-Z.'\- ]{5,40}),?\s*\n\s*(?:Acting |Interim )?Commissioner of ([A-Za-z &]{4,40})", re.M)

# Words that appear in a signature block in the position a name would take.
NOT_A_PERSON = re.compile(r"\b(comptroller|mayor|date|signature|attest|seal|its|by|typed|"
                          r"department|city of chicago|approved|authorized|print|title)\b", re.I)


def looks_like_person(name: str) -> bool:
    w = name.split()
    return (2 <= len(w) <= 4 and not NOT_A_PERSON.search(name)
            and not any(ch.isdigit() for ch in name))


def city_people(text: str) -> dict:
    out = []
    for first, last in CITY_EMAIL.findall(text):
        out.append({"name": f"{first} {last}".replace("-", " ").title(),
                    "role": "mailbox", "email": f"{first}.{last}@cityofchicago.org".lower()})
    for num, name, phone in BUYER_LINE.findall(text):
        nm = " ".join(name.split()).title()
        if looks_like_person(nm):
            out.append({"name": nm, "role": "buyer", "employee_no": num, "phone": phone})
    for name in CPO_SIGN.findall(text):
        nm = " ".join(name.split())
        if looks_like_person(nm):
            out.append({"name": nm.title(), "role": "chief procurement officer"})
    for name, dept in COMMISSIONER.findall(text):
        nm = " ".join(name.split())
        if looks_like_person(nm):
            out.append({"name": nm.title(), "role": "commissioner",
                        "department": " ".join(dept.split())})
    seen, uniq = set(), []
    for p in out:
        k = (p["name"].lower(), p["role"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return {"people": uniq}


# Any of the four places a city employee is named.
CITY_PEOPLE_SIG = re.compile(r"@cityofchicago\.org|^BUYER:|Chief Procurement Officer|Commissioner of", re.M)


FORMS = {
    "eds_certificate":     ("CERTIFICATE OF FILING FOR", eds_certificate),
    "contract_summary":    ("Contract Summary Sheet", contract_summary),
    "modification_summary": ("Modification Summary Report", modification_summary),
    "cdot_modification":   ("REQUEST FOR CONTRACT MODIFICATION", cdot_modification),
    # Selected by pattern rather than by one string: see city_people's comment.
    "city_people":         (CITY_PEOPLE_SIG, city_people),
}



def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("corpus_dir", type=Path, default=Path("data/chicago/2022-2026"), nargs="?")
    p.add_argument("--form", choices=list(FORMS), default=None)
    args = p.parse_args()

    corpus = args.corpus_dir / "corpus"
    out_dir = args.corpus_dir / "forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [args.form] if args.form else list(FORMS)

    pages = []
    for f in sorted(corpus.glob("*.jsonl")):
        for line in open(f):
            pages.append(json.loads(line))

    for name in wanted:
        sig, fn = FORMS[name]
        rows = []
        for r in pages:
            if isinstance(sig, str):
                if sig.lower() not in r["text"].lower():
                    continue
            elif not sig.search(r["text"]):
                continue
            row = fn(r["text"], r["doc_id"]) if name == "modification_summary" else fn(r["text"])
            row.update(page_id=f'{r["doc_id"]}#{r["page"]}', doc_id=r["doc_id"], page=r["page"],
                       po_number=r.get("po_number", ""), spec_number=r.get("spec_number", ""),
                       vendor_name=r.get("vendor_name", ""))
            rows.append(row)
        path = out_dir / f"{name}.jsonl"
        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"\n{name}: {len(rows):,} pagine -> {path}")
        if not rows:
            continue
        keys = [k for k in rows[0] if not k.startswith("_") and
                k not in ("page_id", "doc_id", "page", "po_number", "spec_number", "vendor_name")]
        got = collections.Counter()
        for row in rows:
            for k in keys:
                if row.get(k):
                    got[k] += 1
        print("  " + "  ".join(f"{k} {got[k]*100//len(rows)}%" for k in keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
