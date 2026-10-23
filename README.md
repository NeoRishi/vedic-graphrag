# Vedic GraphRAG

A GraphRAG pipeline that turns an interlinked Obsidian knowledge base on Ayurveda, Yoga Shastra and Jyotisha into a Neo4j knowledge graph, then answers questions with cited, source-traceable responses.

Built by Hrishikesh, founder of NeoRishi Wellness, as the retrieval layer for personalised, explainable wellness guidance.

## Why GraphRAG here

The knowledge base is already a graph written as text: every page carries typed frontmatter (domain, pillar, dosha relevance, product module), links to other concepts with `[[wikilinks]]`, and cites its raw sources with `[Source: file.md]`. Plain RAG throws that structure away. This pipeline keeps it and uses it at query time.

## Pipeline

```
Markdown wiki
   │  import_wiki.py   parse frontmatter, wikilinks, citations
   ▼
Neo4j graph   (Note, Chunk, Dosha, Pillar, Module, Domain, Source, Stub)
   │  build_chunks.py  split by ## heading, embed, vector index
   ▼
Question ─► [1] vector search (30 candidates)
            [2] graph re-rank: dosha filter, dosha and module boosts, max 2 chunks per note
            [3] graph expansion: strongest linked concepts, cited raw sources, BRIDGE and CONTRADICTION flags
            [4] LLM answers ONLY from that context, with [P1] style citations
```

### Graph model

| Node | Comes from |
|---|---|
| `Note`, `Chunk` | each wiki page, split at `##` headings |
| `Dosha`, `Pillar`, `Module`, `Domain` | frontmatter fields |
| `Source` | `[Source: ...]` citations |
| `Stub` | concepts linked to but not yet written (a knowledge gap list for free) |

Relationships: `HAS_CHUNK`, `LINKS_TO {count}`, `CITES`, `RELEVANT_TO_DOSHA`, `SERVES_PILLAR`, `FEEDS_MODULE`, `IN_DOMAIN`.

## Plain RAG vs GraphRAG

See [`examples/compare_vata_autumn_sleep.md`](examples/compare_vata_autumn_sleep.md) for one question run both ways on the full private knowledge base (100 pages, 2,083 links).

What GraphRAG adds in that run:
- **Traceability:** answers name the raw source files behind each passage, via `CITES`.
- **Diversity:** the per-note cap stops near-duplicate sections from crowding out other evidence.
- **Personalisation:** dosha and module signals from the graph re-rank passages toward the user's profile. In this run, plain RAG pulled a Kapha-tagged spring (Vasanta) sleep passage; GraphRAG filtered it out and brought in the Vata Dosha balancing section instead.

What it showed still needs work (and why it matters for ontology design):
- Dosha tags sit on whole pages, while dosha-specific advice sits in sections, so 74 of 100 pages read as "tridoshic" and the filter has little to remove. Next step: tag at chunk level.
- "Kapha" means both a constitution and a time of day (Kapha kala, 7 to 10 PM). Text search cannot tell them apart; the ontology needs two distinct concepts.
- Season (Ritu) is not yet modelled, so seasonal advice cannot be scoped to the current ritu.

## Run it

Use a **fresh, empty** Neo4j Aura Free instance: `build_chunks.py` removes chunks that are not in the current wiki.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in Neo4j and OpenAI credentials

python import_wiki.py --dry-run   # 15 notes, 394 links, 41 sources, 79 stubs
python import_wiki.py
python build_chunks.py            # embeds chunks, creates the vector index

python ask.py "I'm Vata dominant, it's autumn, and I sleep badly. What should my evening look like?" \
  --dosha vata --module routines --compare
```

Flags: `--compare` runs plain RAG and GraphRAG side by side, `--no-llm` shows retrieval only, `--show-context` prints the exact context sent to the model.

## Sample data

`sample_wiki/` holds 15 of the 100 pages (doshas, prakriti, dinacharya, ritucharya, sleep, pranayama, agni, pramana, darshanas). Links to pages outside the sample become `Stub` nodes. The full knowledge base is private.

## Related

**NyAI**: a Nyaya-epistemology explainability layer that structures machine reasoning as the five-step Pañcāvayava inference and checks it against the hetvābhāsa (fallacy) types. Presented at IIT Delhi, April 2026.

## Stack

Python, Neo4j Aura (Cypher, native vector index), OpenAI embeddings (`text-embedding-3-small`) and chat models.

## Note

For research and education. Not medical advice.
