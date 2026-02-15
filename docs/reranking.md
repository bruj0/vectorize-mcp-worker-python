# Reranking in Vectorize

## What Is Reranking?

Reranking is a second-pass relevance refinement step that runs after initial retrieval. Where embedding-based vector search and BM25 keyword search are fast but approximate, a **cross-encoder reranker** reads the query and each candidate document *together* to produce a more accurate relevance score. The tradeoff is latency for precision.

In a typical RAG pipeline, the retrieval stage casts a wide net (fast, recall-oriented), and the reranker narrows it down (slow, precision-oriented). This two-stage design is standard in production search systems.

## Why Reranking Matters

### BM25 Keyword Search

BM25 (Best Matching 25) is a ranking function from information retrieval that scores documents by how well they match a query's exact terms. It's the algorithm behind most traditional search engines and remains hard to beat for exact keyword matching.

**How it works:**

For each query term in a document, BM25 computes:

```
score(term, doc) = IDF(term) × TF(term, doc)
```

Where:

- **IDF (Inverse Document Frequency)** -- how rare the term is across the entire corpus. Rare terms ("kubernetes") contribute more than common terms ("the"). In this codebase:

```python
idf = log((N - df + 0.5) / (df + 0.5) + 1)
#  N  = total documents in corpus
#  df = number of documents containing this term
```

- **TF (Term Frequency)** -- how often the term appears in this specific document, with diminishing returns (the 10th occurrence of "rust" matters less than the 1st) and length normalization (a 50-word doc mentioning "rust" 3 times is more relevant than a 5000-word doc mentioning it 3 times):

```python
tf = (freq × (k1 + 1)) / (freq + k1 × (1 - b + b × (doc_length / avg_doc_length)))
#  freq       = occurrences of term in this document
#  k1 = 1.2   = saturation parameter (how fast TF diminishes)
#  b  = 0.75  = length normalization weight (0 = no normalization, 1 = full)
```

A document's total BM25 score is the sum across all query terms.

**Preprocessing pipeline** (implemented in `src/keyword_search.py`):

1. Lowercase the text
2. Replace non-word characters with spaces
3. Split on whitespace
4. Filter tokens shorter than 3 characters
5. Remove stop words ("the", "a", "is", "for", etc.)

**What BM25 is good at:**

- Exact matches: searching for `"RuntimeError"` finds documents containing that exact string
- Proper nouns, IDs, error codes, jargon that embeddings might not handle well
- Zero-shot -- no model training needed, works on any text corpus

**What BM25 misses:**

- Semantic similarity: `"car"` will not match `"automobile"`
- Context: `"bank"` (financial) and `"bank"` (river) are treated identically
- Paraphrases: `"how to fix a bug"` won't match `"debugging techniques"`

This is exactly why the pipeline combines BM25 with vector search -- they cover each other's blind spots.

### The Problem with First-Stage Retrieval

Vector search (cosine similarity on embeddings) and keyword search (BM25) both have blind spots:

| Method | Strength | Weakness |
|--------|----------|----------|
| **Vector search** | Captures semantic meaning ("car" matches "automobile") | Misses exact keyword matches; embeddings compress nuance |
| **BM25 keyword** | Exact term matching; good for names, IDs, jargon | No semantic understanding ("car" won't match "automobile") |
| **RRF fusion** | Combines both signals | Still limited to the quality of each individual ranker |

Reciprocal Rank Fusion (RRF) merges the two ranked lists, but it only considers *rank position*, not actual relevance. A document at rank 3 in vector search gets the same RRF contribution regardless of whether its cosine similarity was 0.95 or 0.60.

### What the Reranker Adds

A cross-encoder processes `(query, document)` pairs jointly through a transformer, producing a single relevance score. Unlike bi-encoders (used for embeddings), cross-encoders see both texts simultaneously, enabling:

- **Token-level interaction** between query and document
- **Better handling of negation**, qualifiers, and subtle meaning
- **More accurate ordering** within the top results

The cost is that cross-encoders can't be pre-computed -- they must run at query time for each candidate, which is why we only rerank the top 10 results, not the entire corpus.

## Implementation in This Codebase

### Search Pipeline

```
Query
  │
  ├──► Embed query (BGE-small, 384 dims)
  │       │
  │       └──► Vector search (Vectorize, top_k × 2 candidates)
  │
  └──► Tokenize query (BM25)
          │
          └──► Keyword search (D1, top_k × 2 candidates)
                    │
                    ▼
           Reciprocal Rank Fusion (k=60)
                    │
                    ▼
           Reranking (top 10 RRF results)    ◄── optional, on by default
                    │
                    ▼
           Final sort by fused score
                    │
                    ▼
           Return top_k results
```

### Components

| Component | File | Role |
|-----------|------|------|
| `HybridSearchEngine` | `src/hybrid_search.py` | Orchestrates the full pipeline: embed → vector search → BM25 → RRF → rerank |
| `CloudflareAIProvider.rerank()` | `src/bindings/ai.py` | Calls Workers AI with the reranker model |
| `AIProvider.rerank()` | `src/protocols.py` | Protocol abstraction for testability |
| `HybridSearchResult.reranker_score` | `src/models.py` | Stores the per-result reranker score |
| Search endpoints | `src/entry.py` | Passes `rerank` body parameter to the engine |

### Why BGE-Reranker-Base

**BGE** stands for **BAAI General Embedding** -- a family of models from the Beijing Academy of Artificial Intelligence (BAAI) designed specifically for retrieval tasks. The BGE family includes both embedding models (bi-encoders) and reranking models (cross-encoders), trained together on the same data so they complement each other.

This codebase uses two BGE models:

| Model | Type | Role | Dimensions / Output |
|-------|------|------|---------------------|
| `@cf/baai/bge-small-en-v1.5` | Bi-encoder | Embedding generation | 384-dim vector |
| `@cf/baai/bge-reranker-base` | Cross-encoder | Reranking | Single relevance score |

**Why BGE specifically?**

- **Matched training**: The embedding and reranker models are from the same family, trained on overlapping datasets. This means the reranker understands the same notion of "relevance" that the embeddings capture, but with higher fidelity.
- **Available on Workers AI**: Cloudflare hosts both models on their inference platform, so there's no external API dependency or cold-start latency.
- **Strong benchmark performance**: BGE models consistently rank near the top of the MTEB (Massive Text Embedding Benchmark) leaderboard for their size class. `bge-reranker-base` is 278M parameters -- large enough to be accurate, small enough to run with acceptable latency.
- **English-optimized**: The `-en-` variant is tuned for English text, which matches the primary use case.

### What "Cross-Encoder" Means (and Why It Matters)

The term "cross-encoder" describes the model's architecture and how it differs from the bi-encoder used for embedding.

**Bi-encoder** (used for embeddings):

```
Query  ──► Encoder ──► query_vector   ──┐
                                         ├──► cosine_similarity(q, d) = score
Document ──► Encoder ──► doc_vector   ──┘
```

The query and document are encoded **independently** into fixed-size vectors. Similarity is computed afterward with a simple distance metric (cosine similarity). This is fast because document vectors are pre-computed at ingestion time -- at query time you only encode the query once and compare it against all stored vectors.

The tradeoff: because the encoder never sees query and document together, it can't model fine-grained interactions between them. The 384-dimensional vector is a lossy compression of the full text.

**Cross-encoder** (used for reranking):

```
[CLS] Query [SEP] Document [SEP] ──► Transformer ──► score
```

The query and document are **concatenated** and fed through the transformer together. The self-attention mechanism sees every token from both texts simultaneously, enabling:

- **Token-level cross-attention**: The model can match "Rust" in the query to "borrow checker" in the document because it processes both in the same forward pass.
- **Negation awareness**: A bi-encoder might score "Rust does NOT use garbage collection" similarly to "Rust uses garbage collection" because both contain the same words. The cross-encoder processes the full sequence and understands the negation.
- **Contextual disambiguation**: "Python" (the language) vs "python" (the snake) can be resolved when the cross-encoder sees the surrounding query context.

The tradeoff: you can't pre-compute anything. Every `(query, document)` pair requires a full forward pass through the transformer. For 10 candidates, that's 10 forward passes. For 10,000 candidates, it would be prohibitively slow -- which is exactly why reranking is applied only to the top 10 results after the fast retrieval stage.

### Algorithm Detail

#### 1. RRF Fusion (before reranking)

Vector and keyword results are merged using Reciprocal Rank Fusion:

```python
# For each result at position `rank` in a ranked list:
rrf_score += 1.0 / (k + rank + 1)    # k = 60
```

Documents appearing in both lists get contributions from both. The constant `k=60` dampens the influence of exact rank position.

#### 2. Cross-Encoder Reranking

Only the **top 10** RRF results are sent to the reranker. The reranker receives the query and each document's content as a `(query, context)` pair:

```python
reranker_scores = await ai_provider.rerank(
    query, [r.content for r in top_results]
)
```

The Workers AI call looks like:

```python
ai.run("@cf/baai/bge-reranker-base", {
    "query": "memory safety without garbage collection",
    "contexts": [
        {"text": "Rust achieves memory safety through ownership..."},
        {"text": "Python uses garbage collection for memory..."},
        ...
    ]
})
```

Each context gets a relevance score (0.0–1.0).

#### 3. Score Fusion

The RRF score and reranker score are combined with weighted linear interpolation:

```python
final_score = rrf_score * 0.4 + reranker_score * 0.6
```

The reranker gets 60% weight because it produces higher-quality relevance judgments. The RRF score retains 40% to preserve signal from the retrieval stage (especially for results where vector and keyword search agreed).

#### 4. Graceful Degradation

If the reranker call fails (network error, model timeout, etc.), the pipeline continues with the RRF-only scores. Search never breaks because of a reranker failure:

```python
except Exception as exc:
    log.warn("search.rerank_failed", exc=exc)
    # results keep their RRF scores, search continues
```

### API Usage

#### Request

Both `/search/multimodal` and `/search/documents` accept the `rerank` parameter:

```json
POST /search/multimodal
{
    "query": "memory safety without garbage collection",
    "topK": 5,
    "rerank": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rerank` | `bool` | `true` | Enable cross-encoder reranking |

#### Response

Each result includes per-source scores for transparency:

```json
{
    "results": [
        {
            "id": "chunk-abc-0",
            "score": 0.72,
            "snippet": "Rust achieves memory safety through its ownership system...",
            "scores": {
                "vector": 0.91,
                "keyword": 3.42,
                "reranker": 0.88
            }
        },
        {
            "id": "chunk-def-0",
            "score": 0.45,
            "snippet": "Go provides garbage collection but lacks Rust's guarantees...",
            "scores": {
                "vector": 0.85,
                "keyword": null,
                "reranker": 0.31
            }
        }
    ],
    "performance": {
        "embeddingTime": "25ms",
        "vectorSearchTime": "15ms",
        "keywordSearchTime": "30ms",
        "rerankerTime": "120ms",
        "totalTime": "195ms"
    }
}
```

Note: `scores.keyword` is `null` when a result came only from vector search (and vice versa).

#### CLI / MCP Tool

```bash
# With reranking (default)
vectorize-mcp search multimodal "memory safety" --top-k 5 --rerank

# Without reranking
vectorize-mcp search multimodal "memory safety" --top-k 5 --no-rerank
```

## Concrete Example: When Reranking Changes Results

Consider the query **"how does Rust prevent use-after-free bugs"**.

### Without Reranking (RRF only)

| Rank | Content | Vector Score | BM25 Score | RRF Score |
|------|---------|-------------|------------|-----------|
| 1 | "Rust's ownership model ensures memory is freed exactly once..." | 0.89 | 2.1 | 0.032 |
| 2 | "Common C++ bugs include use-after-free, double free..." | 0.82 | 3.8 | 0.031 |
| 3 | "The borrow checker prevents dangling references at compile time..." | 0.91 | 0.0 | 0.016 |

Result #2 ranks high because BM25 loves the exact terms "use-after-free" and "bugs", even though the document is about C++ problems, not Rust solutions.

### With Reranking

| Rank | Content | RRF Score | Reranker Score | Final Score |
|------|---------|-----------|---------------|-------------|
| 1 | "The borrow checker prevents dangling references at compile time..." | 0.016 | 0.94 | 0.571 |
| 2 | "Rust's ownership model ensures memory is freed exactly once..." | 0.032 | 0.87 | 0.535 |
| 3 | "Common C++ bugs include use-after-free, double free..." | 0.031 | 0.22 | 0.144 |

The cross-encoder correctly identifies that the borrow checker document directly answers the question, and demotes the C++ document that merely contains matching keywords.

## Performance and Cost Considerations

| Aspect | Detail |
|--------|--------|
| **Latency** | Reranking typically adds ~100–150ms. It's usually the slowest step in the pipeline. |
| **Cost** | `bge-reranker-base` is billed as "Medium" tier on Workers AI, vs "Low" for embeddings. |
| **Candidate limit** | Fixed at 10. This bounds the latency regardless of `topK`. |
| **Caching** | Results are cached for 60s. Cache key includes `use_reranker`, so reranked and non-reranked results are cached separately. |

### When to Disable Reranking

- **Latency-critical paths**: If you need sub-50ms search, disable reranking with `"rerank": false`.
- **High-volume, low-stakes queries**: Autocomplete, faceted browsing, or exploratory search where precision matters less.
- **Cost optimization**: If you're hitting Workers AI rate limits or want to reduce inference costs.

### When Reranking Is Most Valuable

- **RAG pipelines**: The LLM's answer quality is directly proportional to retrieval precision. Reranking is the cheapest way to improve RAG output.
- **Ambiguous queries**: Short queries or queries with multiple interpretations benefit most from cross-encoder judgment.
- **Mixed-modality corpora**: When results include both text documents and image descriptions, the reranker helps normalize relevance across content types.

## Codebase References

- **Pipeline orchestration**: `src/hybrid_search.py` -- `HybridSearchEngine.search()`, lines 79–169
- **Reranker binding**: `src/bindings/ai.py` -- `CloudflareAIProvider.rerank()`, lines 49–70
- **Protocol contract**: `src/protocols.py` -- `AIProvider.rerank()`, lines 136–138
- **Data model**: `src/models.py` -- `HybridSearchResult.reranker_score`, line 66
- **API endpoint**: `src/entry.py` -- search handler, lines 210–271
- **Unit tests**: `tests/unit/test_hybrid_search.py` -- `test_search_with_reranker`, `test_reranker_failure_graceful`
