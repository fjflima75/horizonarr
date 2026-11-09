"""Release-name matching: is this torrent title the game we are looking for?"""
import difflib
import re

_NOISE = re.compile(
    r"\b(v\d[\w.]*|repack|multi\d*|nsw|nsp|nsz|xci|pkg|iso|update|dlc|build \d+|proper|internal|"
    r"deluxe|ultimate|complete|goty|edition|remastered|incl|\d+ dlcs?)\b")


def clean(title):
    """Lower case, no brackets, no scene/release noise, single spaces."""
    title = re.sub(r"[\[(].*?[\])]", " ", (title or "").lower())
    title = title.replace("&", " and ").replace("_", " ")
    title = _NOISE.sub(" ", title)  # before dots become spaces, so "v1.0.2" goes as one token
    title = title.replace(".", " ")
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def similarity(wanted, release_title):
    """0..1. Compares the wanted name with the start of the release title, so trailing tags don't count."""
    want = clean(wanted)
    got = clean(release_title)
    if not want or not got:
        return 0.0
    return difflib.SequenceMatcher(None, want, got[:len(want) + 12]).ratio()


def best_release(wanted, releases, min_similarity=0.65, min_seeders=2):
    """The best-seeded release whose title matches, as a small dict, or None."""
    best = None
    for r in releases or []:
        seeders = r.get("seeders") or 0
        if seeders < min_seeders or similarity(wanted, r.get("title", "")) < min_similarity:
            continue
        if best is None or seeders > best["seeders"]:
            best = {"title": r.get("title"), "seeders": seeders, "size": r.get("size") or 0,
                    "indexer": r.get("indexer")}
    return best


def same_title(a, b):
    """Loose equality used to link a library entry or a torrent to a game."""
    ca, cb = clean(a), clean(b)
    return bool(ca) and (ca == cb or (len(ca) > 6 and cb.startswith(ca)))
