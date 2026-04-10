#!/usr/bin/env python3
"""
Script 3: Generate Q&A dataset from parsed markdown for fine-tuning.

Input:
  tax_data/parsed/    — Markdown files from 02_parse_to_markdown.py
  tax_data/parsed/manifest.json — Document index

Output:
  tax_data/datasets/tax_qa.jsonl — Q&A pairs in instruction format

Uses Claude Code bridge (OpenAI-compatible API on localhost:8787) for LLM calls.

Usage:
  python tax_data/03_generate_qa.py
  python tax_data/03_generate_qa.py --max-docs 10         # test run
  python tax_data/03_generate_qa.py --max-chunks 5        # test run by chunks
  python tax_data/03_generate_qa.py --resume               # continue from last checkpoint
  python tax_data/03_generate_qa.py --stats                # show dataset stats
  python tax_data/03_generate_qa.py --dry-run              # show chunks without LLM

  # Override bridge URL:
  BRIDGE_URL=http://127.0.0.1:8787 python tax_data/03_generate_qa.py
"""

import argparse
import json
import logging
import os
import re
import textwrap
import time
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
PARSED_DIR = BASE_DIR / "parsed"
MANIFEST_PATH = PARSED_DIR / "manifest.json"
DATASETS_DIR = BASE_DIR / "datasets"
OUTPUT_PATH = DATASETS_DIR / "tax_qa.jsonl"
CHECKPOINT_PATH = DATASETS_DIR / ".checkpoint.json"

# Bridge (Claude Code bridge — OpenAI-compatible API)
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8787")
BRIDGE_API_KEY = os.environ.get("BRIDGE_API_KEY", "")

# Chunking
MAX_CHUNK_WORDS = 800
MIN_CHUNK_WORDS = 100

# LLM
MAX_RETRIES = 3
RETRY_DELAY = 5
REQUEST_DELAY = 1.5  # Delay between LLM calls (bridge rate limiting)
LLM_TIMEOUT = 120  # Bridge can be slow (7-30s warmup, long generation)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM via Bridge
# ---------------------------------------------------------------------------

QA_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Irish tax accountant creating a Q&A training dataset.
    Given a chunk of text from revenue.ie (Irish Revenue Commissioners), generate
    question-answer pairs that would help train an AI tax assistant for Irish
    self-employed individuals.

    Rules:
    - Generate 3-5 Q&A pairs per chunk
    - Questions should be natural, as a self-employed person would ask
    - Answers must be factual, based ONLY on the provided text
    - Include the source URL in each answer for reference
    - Mix question types: factual, procedural, calculation-based, scenario-based
    - Use plain English, avoid jargon unless explaining it
    - If the chunk contains tax rates/thresholds, create calculation examples
    - Answers should be comprehensive but concise (2-5 sentences typically)

    Output ONLY valid JSON array, no markdown fences, no explanation:
    [
      {"instruction": "question here", "input": "", "output": "answer here (Source: URL)"},
      ...
    ]
""")


def _build_user_prompt(chunk_text: str, source_url: str, section: str) -> str:
    return (
        f"Section: {section}\n"
        f"Source: {source_url}\n\n"
        f"---\n{chunk_text}\n---\n\n"
        f"Generate Q&A pairs from this revenue.ie content."
    )


def call_bridge(prompt: str, system: str) -> str:
    """Call Claude Code bridge (OpenAI-compatible /v1/chat/completions)."""
    url = f"{BRIDGE_URL}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if BRIDGE_API_KEY:
        headers["Authorization"] = f"Bearer {BRIDGE_API_KEY}"

    payload = {
        "model": "claude",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_llm(prompt: str) -> str:
    """Call LLM with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            return call_bridge(prompt, QA_SYSTEM_PROMPT)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                log.warning(
                    "Bridge call failed (attempt %d): %s. Retrying in %ds...", attempt + 1, e, delay
                )
                time.sleep(delay)
            else:
                raise


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_markdown(content: str, max_words: int = MAX_CHUNK_WORDS) -> list[str]:
    """Split markdown content into chunks by headings, respecting word limits."""
    # Split by headings (## or ###)
    sections = re.split(r"\n(?=#{1,3}\s)", content)

    chunks = []
    current_chunk = []
    current_words = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        words = len(section.split())

        # If single section exceeds max, split by paragraphs
        if words > max_words:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_words = 0

            paragraphs = section.split("\n\n")
            para_chunk = []
            para_words = 0
            for para in paragraphs:
                pw = len(para.split())
                if para_words + pw > max_words and para_chunk:
                    chunks.append("\n\n".join(para_chunk))
                    para_chunk = []
                    para_words = 0
                para_chunk.append(para)
                para_words += pw
            if para_chunk:
                chunks.append("\n\n".join(para_chunk))
            continue

        # Accumulate sections into chunks
        if current_words + words > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_words = 0

        current_chunk.append(section)
        current_words += words

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Filter out tiny chunks
    return [c for c in chunks if len(c.split()) >= MIN_CHUNK_WORDS]


# ---------------------------------------------------------------------------
# JSON parsing from LLM output
# ---------------------------------------------------------------------------


def parse_qa_response(text: str) -> list[dict]:
    """Extract Q&A pairs from LLM response, handling markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                log.warning("Failed to parse LLM response as JSON")
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    valid = []
    for item in data:
        if isinstance(item, dict) and "instruction" in item and "output" in item:
            valid.append(
                {
                    "instruction": str(item["instruction"]).strip(),
                    "input": str(item.get("input", "")).strip(),
                    "output": str(item["output"]).strip(),
                }
            )

    return valid


# ---------------------------------------------------------------------------
# Checkpoint management
# ---------------------------------------------------------------------------


def load_checkpoint() -> set:
    """Load set of already-processed (file, chunk_index) pairs."""
    if CHECKPOINT_PATH.exists():
        data = json.loads(CHECKPOINT_PATH.read_text())
        return {(e["file"], e["chunk"]) for e in data.get("processed", [])}
    return set()


def save_checkpoint(processed: set):
    """Save checkpoint."""
    data = {"processed": [{"file": f, "chunk": c} for f, c in sorted(processed)]}
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def show_stats():
    """Show dataset statistics."""
    if not OUTPUT_PATH.exists():
        print("No dataset found at", OUTPUT_PATH)
        return

    pairs = []
    with open(OUTPUT_PATH) as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))

    print(f"Total Q&A pairs: {len(pairs)}")
    print(f"File size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")

    sources = {}
    for p in pairs:
        url = ""
        match = re.search(r"Source:\s*(https?://\S+)", p.get("output", ""))
        if match:
            url = match.group(1)
        section = "unknown"
        if "/self-assessment" in url:
            section = "self-assessment"
        elif "/vat/" in url:
            section = "vat"
        elif "/tdm/" in url:
            section = "tdm"
        elif "/tax-credits" in url or "/personal-tax-credits" in url:
            section = "tax-credits"
        elif "/usc/" in url:
            section = "usc"
        else:
            section = "other"
        sources[section] = sources.get(section, 0) + 1

    avg_q_len = sum(len(p["instruction"].split()) for p in pairs) / max(len(pairs), 1)
    avg_a_len = sum(len(p["output"].split()) for p in pairs) / max(len(pairs), 1)

    print(f"Avg question length: {avg_q_len:.0f} words")
    print(f"Avg answer length: {avg_a_len:.0f} words")
    print("\nBy section:")
    for s, c in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {s:25s} {c} pairs")


def main():
    parser = argparse.ArgumentParser(description="Generate Q&A dataset from parsed tax docs")
    parser.add_argument("--max-docs", type=int, default=0, help="Limit number of documents (0=all)")
    parser.add_argument("--max-chunks", type=int, default=0, help="Limit total chunks (0=all)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--stats", action="store_true", help="Show dataset stats and exit")
    parser.add_argument("--dry-run", action="store_true", help="Show chunks without calling LLM")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Load manifest
    if not MANIFEST_PATH.exists():
        log.error("Manifest not found. Run 02_parse_to_markdown.py first.")
        return

    manifest = json.loads(MANIFEST_PATH.read_text())
    log.info("Loaded manifest: %d documents", len(manifest))

    # Check bridge health
    if not args.dry_run:
        try:
            resp = requests.get(f"{BRIDGE_URL}/health", timeout=10)
            log.info("Bridge status: %s", resp.json() if resp.ok else resp.status_code)
        except Exception as e:
            log.error("Bridge not available at %s: %s", BRIDGE_URL, e)
            log.error(
                "Make sure Claude Code bridge is running (start orchestrator or bridge_manager)"
            )
            return

    # Prepare output
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    # Load checkpoint
    processed = load_checkpoint() if args.resume else set()
    if processed:
        log.info("Resuming: %d chunks already processed", len(processed))

    # Sort manifest: prioritize high-value sections
    priority_sections = [
        "self-assessment",
        "income-tax",
        "usc",
        "tax-credits",
        "vat",
        "starting-business",
        "form11",
        "tdm-expenses",
        "tdm-self-assessment",
        "tdm-credits",
    ]

    def section_priority(doc):
        s = doc.get("section", "other")
        return priority_sections.index(s) if s in priority_sections else 100

    manifest.sort(key=section_priority)

    if args.max_docs:
        manifest = manifest[: args.max_docs]

    # Process documents
    total_pairs = 0
    total_chunks = 0
    errors = 0
    chunk_limit = args.max_chunks if args.max_chunks else float("inf")

    mode = "a" if args.resume and OUTPUT_PATH.exists() else "w"

    with open(OUTPUT_PATH, mode) as out_f:
        for doc_idx, doc in enumerate(manifest):
            md_path = PARSED_DIR / doc["file"]
            if not md_path.exists():
                continue

            content = md_path.read_text(encoding="utf-8")
            chunks = chunk_markdown(content)

            if not chunks:
                continue

            log.info(
                "[%d/%d] %s — %d chunks (%s)",
                doc_idx + 1,
                len(manifest),
                doc["file"][:60],
                len(chunks),
                doc["section"],
            )

            for chunk_idx, chunk in enumerate(chunks):
                if total_chunks >= chunk_limit:
                    break

                key = (doc["file"], chunk_idx)
                if key in processed:
                    continue

                if args.dry_run:
                    print(f"\n--- {doc['file']} chunk {chunk_idx} ({len(chunk.split())} words) ---")
                    print(chunk[:300] + "..." if len(chunk) > 300 else chunk)
                    total_chunks += 1
                    continue

                # Call LLM via bridge
                user_prompt = _build_user_prompt(chunk, doc.get("url", ""), doc.get("section", ""))
                try:
                    response = call_llm(user_prompt)
                    pairs = parse_qa_response(response)

                    if pairs:
                        for pair in pairs:
                            out_f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                        out_f.flush()
                        total_pairs += len(pairs)
                        log.info("  chunk %d: %d Q&A pairs", chunk_idx, len(pairs))
                    else:
                        log.warning("  chunk %d: no valid pairs from LLM response", chunk_idx)

                except Exception as e:
                    log.error("  chunk %d: LLM error: %s", chunk_idx, e)
                    errors += 1

                processed.add(key)
                total_chunks += 1

                # Save checkpoint every 10 chunks
                if total_chunks % 10 == 0:
                    save_checkpoint(processed)

                time.sleep(REQUEST_DELAY)

            if total_chunks >= chunk_limit:
                log.info("Chunk limit reached (%d)", args.max_chunks)
                break

    # Final checkpoint
    save_checkpoint(processed)

    log.info("=== DONE ===")
    log.info("Documents processed: %d", doc_idx + 1 if manifest else 0)
    log.info("Chunks processed: %d", total_chunks)
    log.info("Q&A pairs generated: %d", total_pairs)
    log.info("Errors: %d", errors)
    log.info("Output: %s", OUTPUT_PATH)

    if not args.dry_run and total_pairs > 0:
        show_stats()


if __name__ == "__main__":
    main()
