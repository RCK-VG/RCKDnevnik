"""Croatian alphabetical ordering.

SQLite sorts text by raw Unicode code point, so č ć đ š ž end up after z and
names like "Čolić" fall to the bottom of the list. We register a custom SQLite
collation ("cro") and put it on the name columns (see models.py db_collation),
so ORDER BY on those columns follows the Croatian alphabet everywhere -
lists, dropdowns and exports - without changing every query.

Digraphs (dž, lj, nj) are deliberately treated as separate letters: that is
ambiguous to detect and very rare in names, while the real problem people hit
is č/ć/đ/š/ž. Sorting is case- and diacritic-insensitive for the primary order
(so "č" sits right after "c"), which is what a name list should do.
"""

import unicodedata

# Croatian alphabet, in order. č comes right after c, đ after d, and so on.
_CRO_LETTERS = "abcčćdđefghijklmnopqrsštuvwxyzž"
_RANK = {ch: i + 1 for i, ch in enumerate(_CRO_LETTERS)}  # +1: separators get 0
_SEPARATORS = " -'"
_AFTER_LETTERS = len(_CRO_LETTERS) + 1


def sort_key(text):
    """A list of integers that sorts by the Croatian alphabet."""
    text = unicodedata.normalize("NFC", text or "").casefold()
    key = []
    for ch in text:
        rank = _RANK.get(ch)
        if rank is not None:
            key.append(rank)
        elif ch in _SEPARATORS:
            key.append(0)  # space/hyphen before letters ("de Sanctis" < "deak")
        else:
            # digits, punctuation, foreign letters: after the alphabet, stable.
            key.append(_AFTER_LETTERS + ord(ch))
    return key


def compare(a, b):
    """SQLite collation callback: -1, 0 or 1.

    Two levels: first the Croatian alphabet (case/diacritic-insensitive), then
    the exact text as a tie-break. The tie-break means only identical strings
    compare equal, so a UNIQUE column (e.g. Subject.name) and exact-match
    filters keep their normal meaning - the collation changes ordering only."""
    ka, kb = sort_key(a), sort_key(b)
    if ka != kb:
        return -1 if ka < kb else 1
    return (a > b) - (a < b)
