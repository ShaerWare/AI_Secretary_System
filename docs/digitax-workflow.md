# DigiTax Assistant — Workflow & Architecture

## Overview

DigiTax — ИИ-ассистент ирландского бу��галтера. Работает внутри AI Secretary System как чат-инстанс (widget/telegram/mobile) с подключёнными RAG-коллекциями по ирландской бухгалтерии.

---

## Workflow: от вопроса пользователя до ответа

```
Пользователь                                                            DigiTax
     │                                                                     │
     │  "How do I file Form 11 as a                                        │
     │   self-employed contractor?"                                        │
     │ ─────────────────────────────────────────────────────────────────►   │
     │                                                                     │
     │              ┌──────────────────────────────────────┐               │
     │              │  1. SYSTEM PROMPT ASSEMBLY            │               │
     │              │                                      │               │
     │              │  Base prompt (per-instance):          │               │
     │              │  "You are DigiTax, an Irish           │               │
     │              │   accountancy assistant..."           │               │
     │              │                                      │               │
     │              │  + Agentic RAG suffix:                │               │
     │              │  "У тебя есть инструмент             │               │
     │              │   knowledge_search..."                │               │
     │              │                                      │               │
     │              │  + Web Search suffix:                 │               │
     │              │  "У тебя есть инструмент             │               │
     │              │   web_search..."                      │               │
     │              │                                      │               │
     │              │  + Context files (если есть)          │               │
     │              └──────────┬───────────────────────────┘               │
     │                         │                                           │
     │                         ▼                                           │
     │              ┌──────────────────────────────────────┐               │
     │              │  2. LLM GENERATION (iteration 1)     │               │
     │              │                                      │               │
     │              │  Cloud LLM (Claude/GPT/Gemini)       │               │
     │              │  receives:                           │               │
     │              │  - system prompt + tools list         │               │
     │              │  - chat history                       │               │
     │              │  - user message                       │               │
     │              │                                      │               │
     │              │  LLM decides: "I need to search      │               │
     │              │  the knowledge base first"            │               │
     │              │                                      │               │
     │              │  → tool_call: knowledge_search(       │               │
     │              │      query="Form 11 self-employed     │               │
     │              │      filing Ireland")                 │               │
     │              └──────────┬───────────────────────────┘               │
     │                         │                                           │
     │  ◄─ SSE: tool_start ───┘                                           │
     │  {"name":"knowledge_search",                                        │
     │   "query":"Form 11..."}                                             │
     │                         │                                           │
     │                         ▼                                           │
     │              ┌──────────────────────────────────────┐               │
     │              │  3. RAG SEARCH (parallel engines)    │               │
     │              │                                      │               │
     │              │  ┌─────────┐ ┌──────────┐ ┌───────┐ │               │
     │              │  │  BM25   │ │Embeddings│ │Vector │ │               │
     │              │  │ (Okapi) │ │ (Gemini/ │ │Search │ │               │
     │              │  │         │ │  local)  │ │(Chroma│ │               │
     │              │  │ K1=1.5  │ │          │ │ DB)   │ │               │
     │              │  │ B=0.75  │ │ cosine>  │ │       │ │               │
     │              │  │ score>  │ │ 0.3      │ │ :8003 │ │               │
     │              │  │ 0.3     │ │          │ │       │ │               │
     │              │  └────┬────┘ └─────┬────┘ └───┬───┘ │               │
     │              │       └────────┬───┘──────────┘     │               │
     │              │                │                     │               │
     │              │                ▼                     │               │
     │              │     ┌─────────────────┐             │               │
     │              │     │  MERGE & DEDUP  │             │               │
     │              │     │  top-5 by score │             │               │
     │              │     └────────┬────────┘             │               │
     │              │              │                       │               │
     │              │  Searches across 7 collections:      │               │
     │              │  • boards-ie-accountancy             │               │
     │              │  • chartered-accountants-ie          │               │
     │              │  • cpa-ireland                       │               │
     │              │  • accounting-technicians-ie         │               │
     │              │  • accountant-forums-ireland         │               │
     │              │  • icaew-ireland                     │               │
     │              │  • irish-tax (revenue.ie)            │               │
     │              └──────────┬───────────────────────────┘               │
     │                         │                                           │
     │  ◄─ SSE: tool_end ─────┘                                           │
     │  {"name":"knowledge_search",                                        │
     │   "found": true}                                                    │
     │                         │                                           │
     │                         ▼                                           │
     │              ┌──────────────────────────────────────┐               │
     │              │  4. LLM GENERATION (iteration 2)     │               │
     │              │                                      │               │
     │              │  LLM receives tool result:           │               │
     │              │  "## Self Assessment - Form 11       │               │
     │              │   Form 11 is the annual...           │               │
     │              │   Filing deadline: 31 October..."    │               │
     │              │                                      │               │
     │              │  LLM may:                            │               │
     │              │  a) Generate final answer ✓          │               │
     │              │  b) Call web_search for updates      │               │
     │              │  c) Call knowledge_search again      │               │
     │              │     with refined query               │               │
     │              └──────────┬───────────────────────────┘               │
     │                         │                                           │
     │  ◄─ SSE: chunk ────────┘  (streaming response)                     │
     │  "To file Form 11 as a self-employed contractor                     │
     │   in Ireland, here's what you need to know:                         │
     │   1. **Deadline**: 31 October (or mid-November                      │
     │      via ROS online filing)..."                                     │
     │                                                                     │
     │  ◄─ SSE: assistant_message (saved to DB)                           │
     │  ◄─ SSE: done                                                      │
```

---

## UML: Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AI Secretary System                            │
│                                                                          │
│  ┌──────────────────────┐    ┌──────────────────────────────────────┐   │
│  │  CHANNELS (входы)     │    │  CHAT ENGINE (modules/chat/)         │   │
│  │                       │    │                                      │   │
│  │  ┌─────────────────┐ │    │  ┌──────────┐    ┌──────────────��┐  │   │
│  │  │ Widget Instance  │─┼───►│  │  Router  │───►│   Facade      │  │   │
│  │  │ (digitax.ie)     │ │    │  │          │    │ (ChatService  │  │   │
│  │  │                  │ │    │  │ resolves: │    │  Impl)        │  │   │
│  │  │ system_prompt:   │ │    │  │ • RAG cfg│    │               │  │   │
│  │  │ "You are DigiTax │ │    │  │ • LLM    │    │ • stream_     │  │   │
│  │  │  assistant..."   │ │    │  │ • prompt  │    │   message()   │  │   │
│  │  │                  │ │    │  │          │    │ • agentic     │  │   │
│  │  │ rag_mode:        │ │    │  └──────────┘    │   loop        │  │   │
│  │  │  "selected"      │ │    │                  │ • tool exec   │  │   │
│  │  │                  │ │    │                  └───────┬───────┘  │   │
│  │  │ collection_ids:  │ │    │                          │          │   │
│  │  │  [9,10,11,12,    │ │    │                          │          │   │
│  │  │   13,14,8]       │ │    │                          │          │   │
│  │  └─────────────────┘ │    └──────────────────────────┼──────────┘   │
│  │                       │                               │              │
│  │  ┌─────────────────┐ │                               │              │
│  │  │ Telegram Bot     │─┼───────────────────────────────┘              │
│  │  │ (digitax_bot)    │ │                               │              │
│  │  └─────────────────┘ │                               │              │
│  │                       │                               │              │
│  │  ┌─────────────────┐ │                               │              │
│  │  │ Mobile App       │─┼───────────────────────────────┘              │
│  │  │ Instance         │ │                                              │
│  │  └─────────────────┘ │                                              │
│  └──────────────────────┘                                               │
│                                                                          │
│  ┌──────────────────────┐    ┌──────────────────────────────────────┐   │
│  │  LLM PROVIDERS       │    │  TOOLS (доступны LLM в agentic mode) │   │
│  │                       │    │                                      │   │
│  │  ┌─────────────────┐ │    │  ┌──────────────────────────────┐    │   │
│  │  │ Claude (bridge)  │◄┼───┤  │  knowledge_search(query)     │    │   │
│  │  │ supports_tools ✓ │ │    │  │                              │    │   │
│  │  └─────────────────┘ │    │  │  → WikiRAGService            │    │   │
│  │  ┌─────────────────┐ │    │  │    .retrieve_multi_async()   │    │   │
│  │  │ OpenAI/DeepSeek  │◄┼───┤  │                              │    │   │
│  │  │ supports_tools ✓ │ │    │  │  Returns: top-5 sections    │    │   │
│  │  └─────────────────┘ │    │  │  from selected collections   │    │   │
│  │  ┌─────────────────┐ │    │  └──────────────────────────────┘    │   │
│  │  │ Gemini SDK       │◄┼──┐│                                      │   │
│  │  │ supports_tools ✗ │ │  ││  ┌──────────────────────────────┐    │   │
│  │  │ → one-shot RAG   │ │  ││  │  web_search(query)           │    │   │
│  │  └─────────────────┘ │  ││  │                              │    │   │
│  │  ┌─────────────────┐ │  ││  │  → DuckDuckGo API            │    │   │
│  │  │ vLLM (local)     │◄┼──┤│  │  Returns: top-5 web results │    │   │
│  │  │ supports_tools ✓ │ │  ││  └──────────────────────────────┘    │   │
│  │  └─────────────────┘ │  │└──────────────────────────────────────┘   │
│  └──────────────────────┘  │                                            │
│                             │ fallback: inject RAG                       │
│                             │ context into system                        │
│                             │ prompt (one-shot)                          │
│                             │                                            │
│  ┌──────────────────────────┴───────────────────────────────────────┐   │
│  │  KNOWLEDGE BASE (RAG)                                             │   │
│  │                                                                    │   │
│  │  WikiRAGService (app/services/wiki_rag_service.py)                │   │
│  │                                                                    │   │
│  │  ┌──────────────────────────────────────────────────────────┐     │   │
│  │  │  Per-Collection Indexes                                   │     │   │
│  │  │                                                           │     │   │
│  │  │  ┌─────────────────────┐  ┌──────────────────────────┐  │     │   │
│  │  │  │ irish-tax            │  │ boards-ie-accountancy     │  │     │   │
│  │  │  │ (Revenue.ie)         │  │ (Boards.ie forum)         │  │     │   │
│  │  │  │ ~2400 docs           │  │ 240 docs                  │  │     │   │
│  │  │  │                      │  │                           │  │     │   │
│  │  │  │ Tax legislation,     │  │ Practical Q&A from Irish  │  │     │   │
│  │  │  │ Form 11, VAT,        │  │ accountants: exams, tax,  │  │     │   │
│  │  │  │ self-assessment,     │  │ audit, bookkeeping,       │  │     │   │
│  │  │  │ TDM manuals, USC,    │  │ professional bodies       │  │     │   │
│  │  │  │ PRSI, ROS help       │  │ comparison                │  │     │   │
│  │  │  └─────────────────────┘  └──────────────────────────┘  │     │   │
│  │  │                                                           │     │   │
│  │  │  ┌─────────────────────┐  ┌──────────────────────────┐  │     │   │
│  │  │  │ chartered-           │  │ cpa-ireland               │  │     │   │
│  │  │  │ accountants-ie       │  │ (CPA Ireland)             │  │     │   │
│  │  │  │ 692 docs             │  │ 237 docs                  │  │     │   │
│  │  │  │                      │  │                           │  │     │   │
│  │  │  │ Knowledge centre,    │  │ Technical resources,      │  │     │   │
│  │  │  │ professional         │  │ compliance requirements,  │  │     │   │
│  │  │  │ standards, ethics,   │  │ amalgamation info,        │  │     │   │
│  │  │  │ sustainability,      │  │ CPD, going into practice, │  │     │   │
│  │  │  │ student guides,      │  │ student syllabi           │  │     │   │
│  │  │  │ Brexit impact        │  │                           │  │     │   │
│  │  │  └─────────────────────┘  └──────────────────────────┘  │     │   │
│  │  │                                                           │     │   │
│  │  │  ┌─────────────────────┐  ┌──────────────────────────┐  │     │   │
│  │  │  │ accounting-          │  │ accountant-forums-        │  │     │   │
│  │  │  │ technicians-ie       │  │ ireland                   │  │     │   │
│  │  │  │ 30 docs              │  │ 25 docs                   │  │     │   │
│  │  │  │                      │  │                           │  │     │   │
│  │  │  │ ATI qualification,   │  │ Ireland-specific threads: │  │     │   │
│  │  │  │ apprenticeships,     │  │ Irish VAT, Form 11,      │  │     │   │
│  │  │  │ study routes,        │  │ CGT, dual taxation,      │  │     │   │
│  │  │  │ CPD, employers       │  │ self-employment setup     │  │     │   │
│  │  │  └─────────────────────┘  └──────────────────────────┘  │     │   │
│  │  │                                                           │     │   │
│  │  │  ┌─────────────────────┐                                 │     │   │
│  │  │  │ icaew-ireland        │                                 │     │   │
│  │  │  │ 3 docs               │                                 │     │   │
│  │  │  │                      │                                 │     │   │
│  │  │  │ Accounting standards,│                                 │     │   │
│  │  │  │ doing business,      │                                 │     │   │
│  │  │  │ tax overview         │                                 │     │   │
│  │  │  └─────────────────────┘                                 │     │   │
│  │  └──────────────────────────────────────────────────────────┘     │   │
│  │                                                                    │   │
│  │  Search Engines (parallel, results merged):                       │   │
│  │  ┌───────────���┐  ┌──────────────────┐  ┌─────────────────────┐   │   │
│  │  │ BM25 Okapi  │  │ Semantic         │  │ Vector Search       │   │   │
│  │  │ (built-in)  │  │ Embeddings       │  │ Microservice        │   │   │
│  │  │             │  │                  │  │ (ChromaDB :8003)    │   │   │
│  │  │ RU/EN stem  │  │ paraphrase-      │  │                     │   │   │
│  │  │ header 4x   │  │ multilingual-    │  │ paraphrase-         │   │   │
│  │  │ boost       │  │ MiniLM-L12-v2    │  │ multilingual-       │   │   │
│  │  │             │  │ (384 dims, GPU)  │  │ mpnet-base-v2       │   │   │
│  │  │             │  │ OR               │  │ (768 dims)          │   │   │
│  │  │             │  │ Gemini text-     │  │                     │   │   │
│  │  │             │  │ embedding-004    │  │                     │   │   │
│  │  │             │  │ (768 dims, cloud)│  │                     │   │   │
│  │  └──────┬─────┘  └────────┬─────────┘  └──────────┬──────────┘   │   │
│  │         └─────────────────┼────────────────────────┘              │   │
│  │                           ▼                                        │   │
│  │                  ┌─────────────────┐                               │   │
│  │                  │ Merge & Dedup   │                               │   │
│  │                  │ by (file,title) │                               │   │
│  │                  │ keep max score  │                               │   │
│  │                  │ return top-5    │                               │   │
│  │                  └─────────────────┘                               │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## UML: Sequence Diagram (Agentic RAG)

```
User        Widget/Bot    Router           Facade         LLM Provider    WikiRAG         WebSearch
 │              │            │                │               │              │               │
 │  message     │            │                │               │              │               │
 ├─────────────►│            │                │               │              │               │
 │              │  POST      │                │               │              │               │
 │              ├───────────►│                │               │              │               │
 │              │            │ resolve:       │               │              │               │
 │              │            │ • system_prompt│               │              │               │
 │              │            │ • rag_mode     │               │              │               │
 │              │            │ • collection_ids               │              │               │
 │              │            │ • llm_service  │               │              │               │
 │              │            │                │               │              │               │
 │              │            │ stream_message()               │              │               │
 │              │            ├───────────────►│               │              │               │
 │              │            │                │               │              │               │
 │              │            │                │  ┌──────────────────────┐    │               │
 │              │            │                │  │ _finalize_prompt()   │    │               │
 │              │            │                │  │ + agentic RAG suffix │    │               │
 │              │            │                │  │ + web search suffix  │    │               │
 │              │            │                │  └──────────────────────┘    │               │
 │              │            │                │               │              │               │
 │              │            │                │  ┌─ AGENTIC LOOP (max 10) ─────────────────┐│
 │              │            │                │  │            │              │               ││
 │              │            │                │  │ generate() │              │               ││
 │              │            │                │──┼───────────►│              │               ││
 │              │            │                │  │            │              │               ││
 │              │            │                │  │  tool_call:│              │               ││
 │              │            │                │  │  knowledge_search        │               ││
 │              │            │                │◄─┼────────────│              │               ││
 │              │            │                │  │            │              │               ││
 │  ◄─ SSE: tool_start ─────┼────────────────│  │            │              │               ││
 │              │            │                │  │            │              │               ││
 │              │            │                │  │ retrieve_multi_async()    │               ││
 │              │            │                │──┼────────────┼─────────────►│               ││
 │              │            │                │  │            │   ┌──────────┼───────┐       ││
 │              │            │                │  │            │   │ parallel:│       │       ││
 │              │            │                │  │            │   │ • BM25   │       │       ││
 │              │            │                │  │            │   │ • embed  │       │       ││
 │              │            │                │  │            │   │ • vector │       │       ││
 │              │            │                │  │            │   └──────────┼───────┘       ││
 │              │            │                │  │  top-5     │              │               ││
 │              │            │                │◄─┼────────────┼──────────────│               ││
 │              │            │                │  │            │              │               ││
 │  ◄─ SSE: tool_end ───────┼────────────────│  │            │              │               ││
 │              │            │                │  │            │              │               ││
 │              │            │                │  │ (optional: web_search)    │               ││
 │              │            │                │──┼────────────┼──────────────┼──────────────►││
 │              │            │                │◄─┼────────────┼──────────────┼───────────────││
 │              │            │                │  │            │              │               ││
 │              │            │                │  │ generate() │              │               ││
 │              │            │                │  │ (with tool │              │               ││
 │              │            │                │  │  results)  │              │               ││
 │              │            │                │──┼───────────►│              │               ││
 │              │            │                │  │            │              │               ││
 │  ◄─ SSE: chunk (streaming)┼────────────────│  │  content   │              │               ││
 │  ◄─ SSE: chunk ───────────┼────────────────│  │  deltas    │              │               ││
 │  ◄─ SSE: chunk ───────────┼────────────────│◄─┼────────────│              │               ││
 │              │            │                │  │            │              │               ││
 │              │            │                │  └─ END LOOP (no more tool_calls) ──────────┘│
 │              │            │                │               │              │               │
 │              │            │                │ save to DB    │              │               │
 │  ◄─ SSE: assistant_message┼────────────────│               │              │               │
 │  ◄─ SSE: done ────────────┼────────────────│               │              │               │
 │              │            │                │               │              │               │
```

---

## UML: Fallback Flow (Gemini SDK — one-shot RAG)

```
User        Facade              WikiRAG           Gemini
 │            │                    │                 │
 │ message    │                    │                 │
 ├───────────►│                    │                 │
 │            │                    │                 │
 │            │ _supports_tools()  │                 │
 │            │ → False (Gemini)   │                 │
 │            │                    │                 │
 │            │ _inject_rag_context_async()          │
 │            ├───────────────────►│                 │
 │            │                    │                 │
 │            │  retrieve_multi()  │                 │
 │            │  top-7, max 4000   │                 │
 │            │  chars             │                 │
 │            │◄───────────────────│                 │
 │            │                    │                 │
 │            │ System prompt =    │                 │
 │            │ base_prompt        │                 │
 │            │ + "--- КОНТЕКСТ ---"                 │
 │            │ + RAG results      │                 │
 │            │ + no-tools suffix  │                 │
 │            │                    │                 │
 │            │ generate() ────────┼────────────────►│
 │            │                    │                 │
 │  ◄─ SSE: chunk (streaming) ────┼─────────────────│
 │  ◄─ SSE: chunk ────────────────┼─────────────────│
 │  ◄─ SSE: done ─────────────────│                 │
 │            │                    │                 │
```

---

## Configuration: DigiTax Instance

Для настройки DigiTax-ассистента в админ-панели:

### Widget Instance
```
Name:              DigiTax
System Prompt:     "You are DigiTax, an AI assistant specializing in
                    Irish accountancy, taxation, and financial regulation.
                    Answer questions based on Irish tax law, Revenue
                    guidelines, professional accounting standards (CAI,
                    CPA), and practical accountancy advice. Always cite
                    sources when using knowledge base content. If unsure,
                    recommend consulting a qualified chartered accountant."

LLM Backend:       cloud:{provider_id}  (Claude/GPT recommended for tools)
RAG Mode:          selected
Collection IDs:    [irish-tax, boards-ie-accountancy, chartered-accountants-ie,
                    cpa-ireland, accounting-technicians-ie,
                    accountant-forums-ireland, icaew-ireland]
Web Search:        enabled (for current tax rates, deadlines, news)
```

### Key Parameters

| Parameter | Value | Effect |
|-----------|-------|--------|
| Agentic RAG top_k | 5 | 5 best sections per knowledge_search call |
| One-shot RAG top_k | 7 | 7 sections injected into prompt (Gemini fallback) |
| Max tool iterations | 10 | LLM can call knowledge_search up to 10 times |
| BM25 min score | 0.3 | Garbage filter for keyword search |
| Embedding similarity | 0.3 | Minimum cosine similarity |
| Web search results | 5 | DuckDuckGo results per query |
