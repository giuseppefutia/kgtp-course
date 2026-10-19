"""Module 2's SHACL shapes, run unchanged on module 3's data.

The shapes are read out of the module 2 notebook rather than copied here: a
second copy would drift, and the claim is that THOSE shapes run, not shapes
like them.

They target two classes, `pc:Contract` and `kgtp:ContractRecord`, because the
subclass axiom between them lives in the vocabulary and not in the data, and
SHACL follows subclasses only where the data says so. With the
`rdfsplus-optimized` ruleset on, GraphDB materialises that axiom and
`?c a pc:Contract` reaches 274,646 subjects -- 88,916 contracts plus 185,730
revisions -- none of which carries the type explicitly.
"""

import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LESSON2 = os.path.join(ROOT, "modules", "02-modeling-the-world", "lesson.ipynb")


def shapes_from_module2(include_sparql=True):
    """The turtle blocks out of the notebook, verbatim.

    `include_sparql=False` drops the blocks carrying an sh:SPARQLConstraint, and
    the reason is a scale fact. A SPARQL constraint is evaluated **once per focus
    node**. Module 2 ran kg:RevisionsAreConsecutive over 46 contracts and it
    returned instantly; here the same shape has 274,646 focus nodes, so it is
    274,646 separate GROUP BY queries. Left in, it does not finish.

    Fails loudly if module 2's folder has moved: the notebook is opened by path,
    which is why the module's README asks you to leave it where it is.
    """
    nb = json.load(open(LESSON2))
    src = "\n".join("".join(c["source"]) for c in nb["cells"])
    blocks = re.findall(r'"""\s*(@prefix sh:.*?)"""', src, re.S)
    if not include_sparql:
        blocks = [b for b in blocks if "sh:SPARQLConstraint" not in b]
    turtle = "\n".join(blocks).replace('\\"\\"\\"', '"""')
    names = re.findall(r"(kg:\w+)\s+a\s+sh:NodeShape", turtle)
    return turtle, names
