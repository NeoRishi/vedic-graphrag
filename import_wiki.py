#!/usr/bin/env python3
"""
Import the Obsidian wiki/ folder into Neo4j (Aura).

Usage (from this folder, with the virtual environment active):
    python import_wiki.py --dry-run     # parse only, print what would be created
    python import_wiki.py               # actually write to Neo4j

Credentials are read from a file named .env next to this script:
    NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
    NEO4J_USERNAME=neo4j
    NEO4J_PASSWORD=your-password
    NEO4J_DATABASE=neo4j        (optional)

Safe to re-run: uses MERGE, and refreshes each note's relationships.
"""
import argparse
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WIKI = os.path.normpath(os.path.join(HERE, "sample_wiki"))
SKIP_FILES = {"log"}          # log.md is a changelog, not knowledge
INDEX_FILES = {"index"}       # index.md becomes a special :Index node
NULLS = {"", "null", "none", "~", "n/a"}

# Frontmatter field -> (node label, relationship type)
CATEGORY_FIELDS = {
    "domain": ("Domain", "IN_DOMAIN"),
    "pillar": ("Pillar", "SERVES_PILLAR"),
    "dosha_relevance": ("Dosha", "RELEVANT_TO_DOSHA"),
    "neorishi_module": ("Module", "FEEDS_MODULE"),
}

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SOURCE_RE = re.compile(r"\[Source:\s*([^\]]+)\]", re.IGNORECASE)


# ---------------------------------------------------------------- parsing
def read_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def split_frontmatter(text):
    """Return (dict, body). Handles flat 'key: value' YAML only."""
    meta = {}
    if not text.startswith("---"):
        return meta, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return meta, text
    for line in lines[1:end]:
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, "\n".join(lines[end + 1:])


def clean_values(raw):
    """'vata' -> ['vata'];  '[vata, pitta]' -> ['vata','pitta'];  'null' -> []"""
    raw = (raw or "").strip().strip("[]")
    out = []
    for part in re.split(r"[,;|]", raw):
        part = part.strip().strip('"').strip("'").strip()
        if part.lower() not in NULLS:
            out.append(part.lower())
    return out


def link_target(inner):
    """[[target#heading\\|label]] -> 'target'"""
    t = inner.split("|", 1)[0]
    t = t.rstrip("\\")             # escaped pipe used inside tables
    t = t.split("#", 1)[0].strip()
    if t.lower().endswith(".md"):
        t = t[:-3]
    return t


def first_paragraph(body):
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if b and not b.startswith(("#", ">", "|", "-", "*", "```")):
            return re.sub(r"\s+", " ", b)[:1000]
    return ""


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_wiki(wiki_dir):
    files = sorted(f for f in os.listdir(wiki_dir) if f.endswith(".md"))
    slugs = {f[:-3] for f in files}
    lookup = {}
    for s in slugs:                       # tolerant matching for links
        lookup[s.lower()] = s
        lookup[s.lower().replace(" ", "-")] = s

    notes, index_nodes = [], []
    unreadable = []
    for f in files:
        slug = f[:-3]
        if slug in SKIP_FILES:
            continue
        path = os.path.join(wiki_dir, f)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            unreadable.append((f, str(e)))
            continue

        meta, body = split_frontmatter(text)

        links = Counter()
        for m in LINK_RE.finditer(body):
            tgt = link_target(m.group(1))
            if not tgt:
                continue
            key = tgt.lower()
            resolved = lookup.get(key) or lookup.get(key.replace(" ", "-")) or tgt
            if resolved != slug:
                links[resolved] += 1

        sources = Counter()
        for m in SOURCE_RE.finditer(body):
            for part in re.split(r"[,;]", m.group(1)):
                p = part.strip()
                if p:
                    sources[p] += 1

        categories = []
        for field, (label, rel) in CATEGORY_FIELDS.items():
            for val in clean_values(meta.get(field)):
                categories.append({"label": label, "rel": rel, "name": val})

        record = {
            "slug": slug,
            "title": meta.get("title") or slug.replace("-", " ").title(),
            "path": "wiki/" + f,
            "content": body.strip(),
            "summary": first_paragraph(body),
            "word_count": len(body.split()),
            "created": meta.get("created"),
            "last_updated": meta.get("last_updated"),
            "status": (meta.get("status") or "").lower() or None,
            "source_count": to_int(meta.get("source_count")),
            "bridge_count": len(re.findall(r"^>\s*BRIDGE", body, re.M)),
            "contradiction_count": len(re.findall(r"^>\s*CONTRADICTION", body, re.M)),
            "links": [{"target": t, "count": c} for t, c in links.items()],
            "sources": [{"file": s, "count": c} for s, c in sources.items()],
            "categories": categories,
        }
        (index_nodes if slug in INDEX_FILES else notes).append(record)

    note_slugs = {n["slug"] for n in notes}
    stubs = set()
    for rec in notes + index_nodes:
        for l in rec["links"]:
            if l["target"] not in note_slugs:
                stubs.add(l["target"])
    return notes, index_nodes, sorted(stubs), unreadable


# ---------------------------------------------------------------- writing
CONSTRAINTS = [
    "CREATE CONSTRAINT note_slug IF NOT EXISTS FOR (n:Note) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT index_slug IF NOT EXISTS FOR (n:Index) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT stub_slug IF NOT EXISTS FOR (n:Stub) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT source_file IF NOT EXISTS FOR (n:Source) REQUIRE n.file IS UNIQUE",
    "CREATE CONSTRAINT domain_name IF NOT EXISTS FOR (n:Domain) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT pillar_name IF NOT EXISTS FOR (n:Pillar) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT dosha_name IF NOT EXISTS FOR (n:Dosha) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT module_name IF NOT EXISTS FOR (n:Module) REQUIRE n.name IS UNIQUE",
]

UPSERT_NOTES = """
UNWIND $rows AS r
MERGE (n:Note {slug: r.slug})
SET n.title = r.title, n.path = r.path, n.content = r.content,
    n.summary = r.summary, n.word_count = r.word_count,
    n.created = r.created, n.last_updated = r.last_updated,
    n.status = r.status, n.source_count = r.source_count,
    n.bridge_count = r.bridge_count, n.contradiction_count = r.contradiction_count
REMOVE n:Stub
WITH n
OPTIONAL MATCH (n)-[old:LINKS_TO|CITES|IN_DOMAIN|SERVES_PILLAR|RELEVANT_TO_DOSHA|FEEDS_MODULE]->()
DELETE old
"""

UPSERT_INDEX = """
UNWIND $rows AS r
MERGE (n:Index {slug: r.slug})
SET n.title = r.title, n.path = r.path, n.content = r.content
WITH n
OPTIONAL MATCH (n)-[old:LINKS_TO]->()
DELETE old
"""

UPSERT_STUBS = """
UNWIND $rows AS slug
OPTIONAL MATCH (existing:Note {slug: slug})
WITH slug, existing WHERE existing IS NULL
MERGE (s:Stub {slug: slug})
"""

LINKS = """
UNWIND $rows AS r
MATCH (a {slug: r.src}) WHERE a:Note OR a:Index
UNWIND r.links AS l
CALL {
  WITH l
  OPTIONAL MATCH (t:Note {slug: l.target})
  OPTIONAL MATCH (s:Stub {slug: l.target})
  RETURN coalesce(t, s) AS b
}
WITH a, b, l WHERE b IS NOT NULL
MERGE (a)-[x:LINKS_TO]->(b)
SET x.count = l.count
"""

SOURCES = """
UNWIND $rows AS r
MATCH (a:Note {slug: r.src})
UNWIND r.sources AS s
MERGE (src:Source {file: s.file})
MERGE (a)-[x:CITES]->(src)
SET x.count = s.count
"""

CATEGORY = """
UNWIND $rows AS r
MATCH (a:Note {slug: r.src})
MERGE (c:%s {name: r.name})
MERGE (a)-[:%s]->(c)
"""

CLEANUP = """
MATCH (s:Stub) WHERE NOT ()-[:LINKS_TO]->(s) DETACH DELETE s
"""

COUNTS = """
CALL { MATCH (n:Note) RETURN count(n) AS notes }
CALL { MATCH (n:Stub) RETURN count(n) AS stubs }
CALL { MATCH (n:Source) RETURN count(n) AS sources }
CALL { MATCH ()-[r:LINKS_TO]->() RETURN count(r) AS links }
CALL { MATCH ()-[r:CITES]->() RETURN count(r) AS cites }
RETURN notes, stubs, sources, links, cites
"""


def chunks(seq, n=50):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def write_to_neo4j(env, notes, index_nodes, stubs):
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ImportError:
        sys.exit("The 'neo4j' package is not installed. Activate the venv and run: "
                 "pip install -r requirements.txt")

    uri, user, pwd = env.get("NEO4J_URI"), env.get("NEO4J_USERNAME"), env.get("NEO4J_PASSWORD")
    db = env.get("NEO4J_DATABASE") or "neo4j"
    if not (uri and user and pwd):
        sys.exit("Missing NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD in .env (see .env.example).")

    print("Connecting to %s as %s ..." % (uri, user))
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        driver.verify_connectivity()
    except AuthError:
        sys.exit("Login failed: username or password in .env is wrong.")
    except ServiceUnavailable as e:
        sys.exit("Cannot reach the database. Check NEO4J_URI starts with neo4j+s:// and that "
                 "the Aura instance is Running (not Paused) in the Aura console.\n%s" % e)
    print("Connected.")

    all_src = notes + index_nodes
    with driver.session(database=db) as s:
        print("1/6 constraints");   [s.run(q).consume() for q in CONSTRAINTS]
        print("2/6 notes");
        for c in chunks(notes, 25):
            s.run(UPSERT_NOTES, rows=[{k: v for k, v in n.items()
                                       if k not in ("links", "sources", "categories")} for n in c]).consume()
        s.run(UPSERT_INDEX, rows=[{k: n[k] for k in ("slug", "title", "path", "content")}
                                  for n in index_nodes]).consume()
        print("3/6 stubs");         s.run(UPSERT_STUBS, rows=stubs).consume()
        print("4/6 links")
        for c in chunks(all_src):
            s.run(LINKS, rows=[{"src": n["slug"], "links": n["links"]} for n in c]).consume()
        print("5/6 sources + categories")
        for c in chunks(notes):
            s.run(SOURCES, rows=[{"src": n["slug"], "sources": n["sources"]} for n in c]).consume()
        for field, (label, rel) in CATEGORY_FIELDS.items():
            rows = [{"src": n["slug"], "name": c["name"]}
                    for n in notes for c in n["categories"] if c["label"] == label]
            if rows:
                s.run(CATEGORY % (label, rel), rows=rows).consume()
        print("6/6 cleanup");       s.run(CLEANUP).consume()
        rec = s.run(COUNTS).single()
        print("\nDone. Graph now has: %d notes, %d stubs, %d sources, %d links, %d citations"
              % (rec["notes"], rec["stubs"], rec["sources"], rec["links"], rec["cites"]))
    driver.close()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Import Obsidian wiki into Neo4j")
    ap.add_argument("--dry-run", action="store_true", help="parse only, do not connect")
    ap.add_argument("--wiki", default=DEFAULT_WIKI, help="path to wiki folder")
    args = ap.parse_args()

    if not os.path.isdir(args.wiki):
        sys.exit("wiki folder not found at %s" % args.wiki)

    notes, index_nodes, stubs, unreadable = parse_wiki(args.wiki)
    n_links = sum(len(n["links"]) for n in notes + index_nodes)
    n_cites = sum(len(n["sources"]) for n in notes)
    n_src = len({s["file"] for n in notes for s in n["sources"]})
    cats = Counter((c["label"], c["name"]) for n in notes for c in n["categories"])

    print("Wiki folder: %s" % args.wiki)
    print("Notes: %d | Index nodes: %d | Stubs (links to missing pages): %d" %
          (len(notes), len(index_nodes), len(stubs)))
    print("Distinct LINKS_TO: %d | CITES: %d | distinct Sources: %d" % (n_links, n_cites, n_src))
    print("Category nodes:")
    for label in ("Domain", "Pillar", "Dosha", "Module"):
        vals = sorted((name, c) for (l, name), c in cats.items() if l == label)
        print("  %-7s %s" % (label, ", ".join("%s(%d)" % v for v in vals)))
    if stubs:
        print("Stubs (first 15): %s" % ", ".join(stubs[:15]))
    if unreadable:
        print("WARNING, could not read: %s" % unreadable)

    if args.dry_run:
        print("\nDry run only. Nothing was written.")
        return
    write_to_neo4j(read_env(os.path.join(HERE, ".env")), notes, index_nodes, stubs)


if __name__ == "__main__":
    main()
