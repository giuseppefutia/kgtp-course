"""Measure which facts the extracted pages actually carry.

Counting the pages that mention a topic is not the same as counting the pages
that carry a usable value, and the gap is large enough to invert a decision: the
subcontractor forms appear on 487 contracts and are filled in on 4. So every
field below is declared twice -- a pattern that says the page is about the
topic, and a pattern that says the value is there and legible -- and the report
prints both, on pages and on contracts.

    python3 -m checks.corpus_fields                 # the coverage table
    python3 -m checks.corpus_fields --stratum random # only the sampled stratum
    python3 -m checks.corpus_fields --field eds_pct # what the value pattern matched
    python3 -m checks.corpus_fields --vendor        # the vendor number analysis
    python3 -m checks.corpus_fields --contacts      # the officers named on the covers

Reads data/chicago/corpus/*.jsonl directly rather than the graph, so it runs
before a load and after one. It writes nothing.

Adding a field: write the two patterns here. Storing the resulting number
instead would go stale the way the documents do -- the same reason
check_numbers.py stores queries.
"""

from __future__ import annotations

import argparse
import collections
import csv
import difflib
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "chicago" / "corpus"
CONTRACTS_CSV = sorted((ROOT / "data" / "chicago" / "raw").glob("rsxa-ify5_*.csv"))

MONEY = r"\$\s?[\d][\d,\. ]{2,}"

# field -> (the page is about this, the value is present and legible)
FIELDS = {
    "vendor_number": (
        r"Vendor (?:Number|No\.?)",
        r"Vendor (?:Number|No\.?)\s*[:\.]?\s*[A-Za-z0-9\-]{4,12}"),
    "eds_pct": (
        r"Ownership|Economic Disclosure|\bEDS\b",
        r"\b\d{1,3}(?:\.\d+)?\s?%"),
    "insurance_limit": (
        r"General Liability",
        r"General Liability[\s\S]{0,300}?" + MONEY),
    "contact_person": (
        r"Contact Person",
        r"Contact Person[:\s\.]{0,10}[A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){1,3}"),
    "mod_reason": (
        r"Mod Reason|CONTRACT MODIFICATION|Modification Revision Number",
        r"\b(?:TIME EXTENSION|INCREASE|DECREASE|SCOPE CHANGE|NAME CHANGE|ASSIGNMENT"
        r"|RENEWAL|EXERCISE OPTION|CANCELLATION|TERMINATION)\b"),
    "liquidated_damages": (
        r"[Ll]iquidated [Dd]amages",
        MONEY + r"[^\n]{0,40}?\b(?:per|each|a)\s+(?:calendar\s+|working\s+)?day"),
    "renewal_option": (
        r"option to (?:renew|extend)|renewal option",
        r"(?:option[s]? to (?:renew|extend)|renewal option)[\s\S]{0,200}?"
        r"\b(?:one|two|three|four|five|\d{1,2})\b[\s\S]{0,20}?(?:year|month|period)"),
    "unit_price": (
        r"Unit Price|UNIT PRICE",
        r"(?:Unit Price|UNIT PRICE)[\s\S]{0,200}?" + MONEY),
    "subcontractor_name": (
        r"Name of Subcontractor",
        r"Name of Subcontractor[:\s\.]{0,10}\n?\s*[A-Z][A-Za-z&\.\,' ]{4,}"),
}

VENDOR_NUMBER = re.compile(r"Vendor (?:Number|No\.?)\s*[:\.]?\s*([A-Za-z0-9\-]{4,12})")

CONTACT = re.compile(
    r"Contact Person[:\s\.]{0,10}([A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){1,3})")

# Words that follow a name into the match because the sentence continues. Cut
# from the tail rather than matched around: the cover prints the name and then
# runs straight into the next instruction with no punctuation.
CONTACT_TAIL = {"PLEASE", "PHONE", "EMAIL", "DOLLAR", "VALUE", "NUMBER", "FOR",
                "THE", "DEPT", "CITY", "OF", "CONTRACT", "REFER", "NAME",
                "TITLE", "ADDRESS", "DATE", "VENDOR"}

PAYROLL = sorted((ROOT / "data" / "chicago" / "raw").glob("xzkq-xp2w_*.csv"))


MANIFEST = ROOT / "data" / "chicago" / "corpus_manifest.csv"


def strata():
    """doc_id -> stratum, from the manifest that chose the documents.

    Only `random` supports a frequency: `pinned` and `stratified` were selected
    on purpose, the second one deliberately over-sampling the small cells. A
    percentage over the whole corpus answers "how often in what we fetched",
    which is a different question from "how often in the contracts".
    """
    out = {}
    if not MANIFEST.exists():
        return out
    with open(MANIFEST) as fh:
        for row in csv.DictReader(fh):
            out[f"{row['po_number']}_r{row['revision']}"] = row["stratum"]
    return out


def pages(stratum=None):
    """Yield every extracted page as a dict, one JSONL file per document."""
    keep = strata() if stratum else {}
    for path in sorted(glob.glob(str(CORPUS / "*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                row = json.loads(line)
                if stratum and keep.get(row["doc_id"]) != stratum:
                    continue
                yield row


def coverage(examples_for=None, stratum=None):
    compiled = {k: (re.compile(a), re.compile(b)) for k, (a, b) in FIELDS.items()}
    trig_p, val_p = collections.Counter(), collections.Counter()
    trig_c = collections.defaultdict(set)
    val_c = collections.defaultdict(set)
    examples, n_pages, contracts = [], 0, set()

    for row in pages(stratum):
        n_pages += 1
        contracts.add(row["po_number"])
        for name, (trigger, value) in compiled.items():
            if not trigger.search(row["text"]):
                continue
            trig_p[name] += 1
            trig_c[name].add(row["po_number"])
            found = value.search(row["text"])
            if not found:
                continue
            val_p[name] += 1
            val_c[name].add(row["po_number"])
            if name == examples_for and len(examples) < 20:
                examples.append((row["po_number"], row["page"],
                                 " ".join(found.group(0).split())[:110]))

    scope = f" in stratum '{stratum}'" if stratum else ""
    print(f"{n_pages:,} pages, {len(contracts):,} contracts with text{scope}\n")
    print(f"{'field':<20}{'pages':>8}{'w/ value':>10}{'contracts':>11}"
          f"{'w/ value':>10}{'share':>8}")
    for name in sorted(FIELDS, key=lambda k: -len(val_c[k])):
        share = len(val_c[name]) / len(contracts) if contracts else 0
        print(f"{name:<20}{trig_p[name]:>8,}{val_p[name]:>10,}"
              f"{len(trig_c[name]):>11,}{len(val_c[name]):>10,}{share:>7.0%}")

    if examples_for:
        print(f"\nwhat the value pattern matched for {examples_for}:")
        for po, page, text in examples:
            print(f"  PO {po} p{page}: {text}")


def vendor_numbers():
    """Report the vendor number as an identity key, with its three failure modes.

    The number printed on the cover is not the Vendor ID the contracts CSV
    carries -- different formats, and on 965 of the 1,000 contracts that print
    one they do not correspond (measured 31/8/2026). That makes it a join key
    that exists only in the documents, which is what makes it worth extracting
    and also what leaves it unchecked by anything else.
    """
    per_doc = collections.defaultdict(collections.Counter)
    per_po = collections.defaultdict(collections.Counter)
    for row in pages():
        for hit in VENDOR_NUMBER.findall(row["text"]):
            number = hit.strip().upper().lstrip("0")
            if any(c.isdigit() for c in number):
                per_doc[row["doc_id"]][number] += 1
                per_po[row["po_number"]][number] += 1

    conflicting = [d for d, c in per_doc.items() if len(c) > 1]
    print(f"contracts printing a vendor number: {len(per_po):,}")
    print(f"documents printing more than one:   {len(conflicting):,}"
          f" of {len(per_doc):,}   <- OCR flips a digit")
    for doc in conflicting[:5]:
        print(f"    {doc}: {dict(per_doc[doc])}")
    print(f"contracts disagreeing across revisions: "
          f"{sum(1 for c in per_po.values() if len(c) > 1):,}")

    if not CONTRACTS_CSV:
        print("\ncontracts CSV not in data/chicago/raw, skipping the name pairs")
        return

    names = collections.defaultdict(set)
    with open(CONTRACTS_CSV[-1]) as fh:
        for row in csv.DictReader(fh):
            names[row["Purchase Order (Contract) Number"]].add(row["Vendor Name"])

    # The most frequent reading wins the tie. That hides the disagreement counted
    # above, which is why it is counted above rather than resolved here.
    linked = collections.defaultdict(set)
    per_name = collections.defaultdict(set)
    for po, counts in per_po.items():
        number = counts.most_common(1)[0][0]
        for name in names.get(po, ()):
            linked[number].add(name)
            per_name[name].add(number)

    pairs = []
    for number, group in linked.items():
        group = sorted(group)
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                ratio = difflib.SequenceMatcher(
                    None, group[i].upper(), group[j].upper()).ratio()
                pairs.append((ratio, number, group[i], group[j]))

    joint = [p for p in pairs if re.search(r"JOINT VENTURE|\bJ ?V\b|/", p[2] + p[3], re.I)]
    print(f"\nlegal names linked by a shared vendor number: {len(pairs)} pairs")
    print(f"  of which one side is a joint venture: {len(joint)}"
          f"   <- merging on this key swallows the JV into its parent")
    print(f"  below 0.50 name similarity, so no threshold would ever join them:")
    for ratio, number, a, b in sorted(p for p in pairs if p[0] < 0.50):
        print(f"    {ratio:.2f}  {number:>12}  {a}  <->  {b}")

    repeated = {n: v for n, v in per_name.items() if len(v) > 1}
    print(f"\nlegal names carrying more than one vendor number: {len(repeated)}"
          f" of {len(per_name)}")

    # Split before concluding. Most of a raw count like the one above is the OCR
    # noise already reported, and only what survives both filters says the key
    # itself does not partition -- which is the claim the resolution would rest
    # on. Measured 31/8/2026: 17 names, 2 confusable characters, 5 truncations,
    # 10 genuinely distinct numbers.
    confusable = str.maketrans({"O": "0", "L": "1", "I": "1", "S": "5",
                                "T": "7", "G": "6", "B": "8", "Z": "2"})

    def truncation(nums):
        ordered = sorted(nums, key=len)
        return all(ordered[i + 1].startswith(ordered[i])
                   for i in range(len(ordered) - 1))

    ocr = {n: v for n, v in repeated.items()
           if len({x.translate(confusable) for x in v}) == 1 or truncation(v)}
    distinct = {n: v for n, v in repeated.items() if n not in ocr}
    print(f"  reading errors -- one number misread: {len(ocr)}")
    print(f"  genuinely different numbers: {len(distinct)}"
          f"   <- the key does not partition")
    for name, nums in sorted(distinct.items()):
        print(f"    {name}: {sorted(nums)}")


def contacts():
    """The procurement officers printed on the covers, checked against the payroll.

    The cover names a person -- `Procurement Services Contact Person` -- and the
    payroll names city employees. Nothing links them: this is the only place the
    two sources touch outside a department name, and how many names survive the
    check is what says whether that link is real or an artefact of the parsing.

    Measured 1/9/2026: 315 names on the covers, 47 of them employees, almost all
    in the Department of Procurement Services. The names are not printed here --
    they are real people in a public payroll, and a count answers the question.
    """
    found = collections.Counter()
    orders = collections.defaultdict(set)
    for row in pages():
        for hit in CONTACT.findall(row["text"]):
            parts = hit.upper().split()
            while parts and parts[-1] in CONTACT_TAIL:
                parts.pop()
            if len(parts) >= 2 and all(len(p) > 1 for p in parts):
                name = " ".join(parts[:3])
                found[name] += 1
                orders[name].add(row["po_number"])

    print(f"names read from 'Contact Person': {len(found)}"
          f" over {len(set().union(*orders.values())) if orders else 0} contracts")
    if not PAYROLL:
        print("payroll CSV not in data/chicago/raw, cannot check them")
        return

    employees = collections.defaultdict(set)
    with open(PAYROLL[-1]) as fh:
        reader = csv.DictReader(fh)
        name_col = reader.fieldnames[0]
        dept_col = [c for c in reader.fieldnames if "epart" in c][0]
        for row in reader:
            raw = row[name_col].upper().strip()
            if "," not in raw:
                continue
            last, first = raw.split(",", 1)
            given = first.replace(".", " ").split()
            if given:
                employees[f"{given[0]} {last.strip()}"].add(row[dept_col])

    # A middle name read off the cover is dropped before comparing: the payroll
    # writes one and the cover often does not, and the pair is the same person.
    def match(name):
        parts = name.split()
        if name in employees:
            return name
        if len(parts) == 3 and f"{parts[0]} {parts[2]}" in employees:
            return f"{parts[0]} {parts[2]}"
        return None

    hits = {n: match(n) for n in found if match(n)}
    depts = collections.Counter(d for k in hits.values() for d in employees[k])
    print(f"of those, employees in the payroll: {len(hits)}")
    print(f"contracts they are named on: "
          f"{len(set().union(*(orders[n] for n in hits))) if hits else 0}")
    print("departments they work for:")
    for dept, n in depts.most_common(5):
        print(f"    {n:>3}  {dept}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--field", choices=sorted(FIELDS),
                        help="print what the value pattern matched for one field")
    parser.add_argument("--stratum", choices=("random", "pinned", "stratified"),
                        help="restrict to one stratum of the manifest; only "
                             "`random` supports a frequency")
    parser.add_argument("--vendor", action="store_true",
                        help="the vendor number as an identity key, and its failures")
    parser.add_argument("--contacts", action="store_true",
                        help="the officers named on the covers, checked against the payroll")
    args = parser.parse_args()

    if not CORPUS.exists():
        raise SystemExit(f"no extracted corpus at {CORPUS}")
    if args.contacts:
        contacts()
    elif args.vendor:
        vendor_numbers()
    else:
        coverage(args.field, args.stratum)


if __name__ == "__main__":
    main()
