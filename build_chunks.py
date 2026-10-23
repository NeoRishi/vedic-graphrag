#!/usr/bin/env python3
"""
GraphRAG stages 1 + 2: split wiki notes into chunks, embed them, store in Neo4j.

    python build_chunks.py --dry-run   # show chunking + cost estimate (no API calls)
    python build_chunks.py             # embed new/changed chunks and write them

Each chunk becomes (:Note)-[:HAS_CHUNK]->(:Chunk {id, heading, text, embedding}).
Only chunks whose text changed are re-embedded, so re-runs are nearly free.
"""
import argparse
import hashlib
import re
import sys

from import_wiki import parse_wiki, DEFAULT_WIKI

MAX_WORDS = 450      # target size: big enough for meaning, small enough to be precise
HARD_MAX = 1200      # emergency split for giant tables
MIN_WORDS = 40       # tiny sections get merged into the previous chunk


def split_sections(content):
    """Split markdown into (heading, text) at #, ## and ### headings (ignoring code blocks)."""
    sections, heading, buf, in_fence = [], "Overview", [], False
    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if "\n".join(buf).strip():
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    if "\n".join(buf).strip():
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def pack(pieces, sep, limit):
    out, cur, n = [], [], 0
    for p in pieces:
        w = len(p.split())
        if cur and n + w > limit:
            out.append(sep.join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        out.append(sep.join(cur))
    return out


def split_long(text):
    if len(text.split()) <= MAX_WORDS:
        return [text]
    parts = pack(re.split(r"\n\s*\n", text), "\n\n", MAX_WORDS)
    final = []
    for p in parts:   # a single huge paragraph/table: split by lines
        final.extend(pack(p.splitlines(), "\n", MAX_WORDS) if len(p.split()) > HARD_MAX else [p])
    return final


def chunk_note(note):
    raw = []
    for heading, text in split_sections(note["content"]):
        for piece in split_long(text):
            raw.append([heading, piece])
    merged = []
    for heading, text in raw:
        if merged and len(text.split()) < MIN_WORDS:
            merged[-1][1] += "\n\n" + (heading + ": " if heading != merged[-1][0] else "") + text
        else:
            merged.append([heading, text])
    chunks = []
    for i, (heading, text) in enumerate(merged):
        # The title + heading is prepended before embedding so each chunk "knows" its context.
        embed_text = "%s > %s\n\n%s" % (note["title"], heading, text)
        chunks.append({
            "id": "%s::%03d" % (note["slug"], i),
            "slug": note["slug"],
            "position": i,
            "heading": heading,
            "text": text,
            "words": len(text.split()),
            "embed_text": embed_text,
            "hash": hashlib.sha1(embed_text.encode("utf-8")).hexdigest(),
        })
    return chunks


WRITE = """
UNWIND $rows AS r
MATCH (n:Note {slug: r.slug})
MERGE (c:Chunk {id: r.id})
SET c.heading = r.heading, c.text = r.text, c.position = r.position,
    c.word_count = r.words, c.text_hash = r.hash, c.embedding = r.embedding
MERGE (n)-[:HAS_CHUNK]->(c)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    notes, _, _, _ = parse_wiki(DEFAULT_WIKI)
    chunks = [c for n in notes for c in chunk_note(n)]
    words = sum(c["words"] for c in chunks)
    tokens = int(words * 1.4)
    print("Notes: %d -> Chunks: %d (avg %d words, largest %d words)" %
          (len(notes), len(chunks), words // max(len(chunks), 1), max(c["words"] for c in chunks)))
    print("Approx tokens to embed: %d  (~$%.3f with %s)" % (tokens, tokens / 1e6 * 0.02, "text-embedding-3-small"))
    sample = [c for c in chunks if c["slug"] == "dinacharya"] or chunks[:5]
    print("\nExample, how '%s' is split:" % sample[0]["slug"])
    for c in sample[:8]:
        print("  %-14s %4d words  | %s" % (c["id"].split("::")[1], c["words"], c["heading"][:60]))

    if args.dry_run:
        print("\nDry run only. Nothing was embedded or written.")
        return

    from kb_common import load_env, connect_neo4j, openai_client, embed
    env = load_env()
    client = openai_client(env)
    driver, db = connect_neo4j(env)
    with driver.session(database=db) as s:
        s.run("CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE").consume()
        existing = {r["id"]: r["h"] for r in s.run(
            "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN c.id AS id, c.text_hash AS h")}
        todo = [c for c in chunks if existing.get(c["id"]) != c["hash"]]
        print("\nAlready embedded and unchanged: %d | to embed now: %d" % (len(chunks) - len(todo), len(todo)))
        for i in range(0, len(todo), 100):
            batch = todo[i:i + 100]
            vectors = embed(client, [c["embed_text"] for c in batch])
            rows = []
            for c, v in zip(batch, vectors):
                row = {k: c[k] for k in ("id", "slug", "position", "heading", "text", "words", "hash")}
                row["embedding"] = v
                rows.append(row)
            s.run(WRITE, rows=rows).consume()
            print("  embedded %d / %d" % (min(i + 100, len(todo)), len(todo)))
        removed = s.run("MATCH (c:Chunk) WHERE NOT c.id IN $ids DETACH DELETE c RETURN count(*) AS n",
                        ids=[c["id"] for c in chunks]).single()["n"]
        total = s.run("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n").single()["n"]
    driver.close()
    print("\nDone. %d chunks with embeddings in Neo4j (%d stale chunks removed)." % (total, removed))


if __name__ == "__main__":
    main()
