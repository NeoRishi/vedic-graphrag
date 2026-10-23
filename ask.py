#!/usr/bin/env python3
"""
GraphRAG stages 4 + 5: retrieve context from Neo4j and answer with OpenAI.

    python ask.py "How should my evening routine look in autumn?" --dosha vata --module routines
    python ask.py "..." --dosha vata --compare     # plain RAG vs GraphRAG side by side
    python ask.py "..." --no-llm                   # show retrieved context only (no chat cost)
"""
import argparse
import re
import sys

from kb_common import load_env, connect_neo4j, openai_client, embed, DEFAULT_CHAT_MODEL

TOP_N = 6           # passages given to the LLM
CANDIDATES = 30     # vector hits considered before graph re-ranking
DOSHA_BOOST = 0.04
MODULE_BOOST = 0.02
MAX_PER_NOTE = 2

VECTOR_Q = """
CALL db.index.vector.queryNodes('chunk_embedding', $k, $vec) YIELD node AS c, score
MATCH (n:Note)-[:HAS_CHUNK]->(c)
OPTIONAL MATCH (n)-[:RELEVANT_TO_DOSHA]->(d:Dosha)
OPTIONAL MATCH (n)-[:FEEDS_MODULE]->(m:Module)
RETURN c.id AS id, c.heading AS heading, c.text AS text, score,
       n.slug AS slug, n.title AS title,
       collect(DISTINCT d.name) AS doshas, collect(DISTINCT m.name) AS modules
ORDER BY score DESC
"""

EXPAND_Q = """
UNWIND $slugs AS s
MATCH (n:Note {slug: s})
CALL (n) {
  OPTIONAL MATCH (n)-[l:LINKS_TO]->(nb:Note)
  WITH nb, l ORDER BY l.count DESC
  LIMIT 4
  RETURN collect(CASE WHEN nb IS NULL THEN null
                 ELSE {title: nb.title, summary: nb.summary} END) AS related
}
CALL (n) {
  OPTIONAL MATCH (n)-[:CITES]->(src:Source)
  RETURN collect(src.file) AS sources
}
RETURN n.slug AS slug, n.title AS title, related, sources, n.content AS content
"""

SYSTEM = """You are NeoRishi's knowledge assistant.
Answer ONLY from the context provided. Cite passages inline as [P1], [P2].
When the context names raw sources, list them at the end under 'Sources'.
If a CONTRADICTION flag in the context is relevant, mention it plainly.
If the context is not enough to answer, say what is missing instead of guessing.
Keep Ayurveda, Yoga Shastra and Jyotisha distinct; do not blend them carelessly.
Write in clear, practical language."""


def vector_hits(session, vec, k):
    return [dict(r) for r in session.run(VECTOR_Q, k=k, vec=vec)]


def plain_rag(session, vec):
    return vector_hits(session, vec, TOP_N), []


def graph_rag(session, vec, dosha, module):
    hits = vector_hits(session, vec, CANDIDATES)
    kept = []
    for h in hits:
        ds = h["doshas"]
        # 1. FILTER: drop notes written only for a different dosha
        if dosha and ds and dosha not in ds and "tridoshic" not in ds:
            continue
        # 2. BOOST: exact dosha match, module match
        h["final"] = h["score"]
        if dosha and dosha in ds:
            h["final"] += DOSHA_BOOST
        if module and module in h["modules"]:
            h["final"] += MODULE_BOOST
        kept.append(h)
    kept.sort(key=lambda x: x["final"], reverse=True)
    # 3. DIVERSITY: at most MAX_PER_NOTE chunks per note
    chosen, per_note = [], {}
    for h in kept:
        if per_note.get(h["slug"], 0) < MAX_PER_NOTE:
            chosen.append(h)
            per_note[h["slug"]] = per_note.get(h["slug"], 0) + 1
        if len(chosen) == TOP_N:
            break
    # 4. EXPAND: walk the graph from the chosen notes
    slugs = list(dict.fromkeys(h["slug"] for h in chosen))
    expansion = [dict(r) for r in session.run(EXPAND_Q, slugs=slugs)]
    return chosen, expansion


def flags(content, kind, limit=2):
    lines = [l.lstrip("> ").strip() for l in content.splitlines() if re.match(r"^>\s*%s" % kind, l)]
    return [l[:300] for l in lines[:limit]]


def build_context(passages, expansion):
    parts = []
    for i, p in enumerate(passages, 1):
        parts.append("[P%d] From '%s' (section: %s)\n%s" % (i, p["title"], p["heading"], p["text"]))
    if expansion:
        parts.append("=== Graph context (from the knowledge graph) ===")
        for e in expansion:
            lines = ["Note: %s" % e["title"]]
            rel = [r for r in e["related"] if r and r.get("title")]
            if rel:
                lines.append("  Strongly linked concepts: " + "; ".join(
                    "%s: %s" % (r["title"], (r.get("summary") or "")[:160]) for r in rel))
            if e["sources"]:
                lines.append("  Raw sources cited: " + ", ".join(e["sources"][:8]))
            for f in flags(e["content"] or "", "BRIDGE"):
                lines.append("  " + f)
            for f in flags(e["content"] or "", "CONTRADICTION"):
                lines.append("  " + f)
            parts.append("\n".join(lines))
    return "\n\n".join(parts)


def answer(client, model, question, dosha, module, context):
    import openai
    profile = "User profile: dosha=%s, module=%s" % (dosha or "unknown", module or "any")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": "%s\n\nQuestion: %s\n\nContext:\n%s" % (profile, question, context)}],
        )
    except openai.NotFoundError:
        ids = sorted(m.id for m in client.models.list() if m.id.startswith(("gpt", "o")))
        sys.exit("Chat model '%s' is not available to your key.\nModels you can use:\n  %s\n"
                 "Put one in .env as  OPENAI_CHAT_MODEL=<name>" % (model, "\n  ".join(ids)))
    except openai.AuthenticationError:
        sys.exit("OpenAI rejected the API key. Check OPENAI_API_KEY in .env")
    except openai.RateLimitError as e:
        sys.exit("OpenAI rate limit or no credit (check Billing):\n%s" % e)
    return resp.choices[0].message.content


def show(label, passages):
    print("\n--- %s: retrieved passages ---" % label)
    for i, p in enumerate(passages, 1):
        extra = " (graph score %.3f)" % p["final"] if "final" in p else ""
        print("  [P%d] %.3f%s  %s > %s   doshas=%s" % (
            i, p["score"], extra, p["title"], p["heading"][:50], ",".join(p["doshas"]) or "-"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--dosha", choices=["vata", "pitta", "kapha"])
    ap.add_argument("--module", help="e.g. routines, panchang, breathing, journal")
    ap.add_argument("--compare", action="store_true", help="run plain RAG and GraphRAG side by side")
    ap.add_argument("--no-llm", action="store_true", help="only show retrieval, skip the answer")
    ap.add_argument("--show-context", action="store_true", help="print the full context sent to the LLM")
    args = ap.parse_args()

    env = load_env()
    client = openai_client(env)
    model = env.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    driver, db = connect_neo4j(env)
    qvec = embed(client, [args.question])[0]

    modes = ["Plain RAG", "GraphRAG"] if args.compare else ["GraphRAG"]
    with driver.session(database=db) as s:
        results = {}
        for mode in modes:
            if mode == "Plain RAG":
                results[mode] = plain_rag(s, qvec)
            else:
                results[mode] = graph_rag(s, qvec, args.dosha, args.module)
    driver.close()

    for mode in modes:
        passages, expansion = results[mode]
        show(mode, passages)
        context = build_context(passages, expansion)
        if args.show_context:
            print("\n--- %s: full context ---\n%s" % (mode, context))
        if not args.no_llm:
            print("\n=== %s answer (%s) ===\n" % (mode, model))
            print(answer(client, model, args.question, args.dosha, args.module, context))


if __name__ == "__main__":
    main()
