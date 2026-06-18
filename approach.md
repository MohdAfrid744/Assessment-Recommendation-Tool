# Approach Document: Assessment Recommendation Tool

## 1. Design Choices
Building a fully stateless API required strict adherence to data integrity on every turn. To achieve this, the architecture was decomposed into specific files acting as isolated layers:
1. **API/Validation Layer (`app/main.py`, `app/schemas.py`)**: `main.py` is the FastAPI entry point that exposes the stateless `/chat` and `/health` endpoints. It interfaces with `schemas.py`, which uses strict Pydantic modeling to enforce the 3-key JSON schema.
2. **Retrieval Layer (`app/retriever.py`, `data/shl_catalogue_json.json`)**: `retriever.py` acts as a hybrid search engine mapping the conversational history to the static database inside `shl_catalogue_json.json`.
3. **Orchestration Layer (`app/agent.py`)**: This file is the brain of the agent. It formats the system prompt, manages the LLM cascade (Gemini to Groq), parses the JSON output, and runs the guardrail validation logic.

## 2. Retrieval Setup
To solve the "vocabulary gap" between a hiring manager's vague intent and the catalog's exact terminology, I implemented an **Advanced Sparse Retriever (BM25Okapi)** combined with Intent Heuristics. 
While initial iterations used neural embeddings, I shifted entirely to BM25 to achieve a massive reduction in memory footprint. To maintain the accuracy of semantic search, I built custom heuristic functions that dynamically boost specific assessment types (like Leadership or Behavioral tests) if specific constraints are detected in the natural language query.

## 3. Prompt Design
The prompt employs a "Highly Professional Organizational Psychologist" persona. To force the LLM to follow the non-negotiable JSON schema, I relied heavily on **Few-Shot Prompting**. By injecting strict JSON conversational examples directly into the prompt (one demonstrating clarification, and one demonstrating a final recommendation), the LLM is tightly constrained and prevented from outputting unpredictable conversational padding. 

## 4. Evaluation Approach & Measuring Improvement
To evaluate the agent before submitting, I relied on the provided `eval/evaluate.py` trace scripts and monitored the `Recall@10` metric. To debug the exact payloads being sent and received, I built a custom **Streamlit State Inspector (`app/streamlit_ui.py`)**. This UI file visually proved that the conversation history was being passed statelessly and allowed me to intercept JSON schema errors in real-time. Improvement was measured by observing the absolute elimination of `JSONDecodeError` rates in the backend logs as prompt engineering and the regex fallback advanced.

## 5. What Didn't Work
1. **OOM Crashes (Neural Embeddings):** Initially, the architecture utilized `SentenceTransformers` to provide dense semantic search. However, loading PyTorch models caused Out-Of-Memory (OOM) crashes on 512MB cloud free tiers like Render.com.
   - *Fix:* I aggressively refactored the retrieval engine to rely purely on `BM25Okapi` (a highly memory-efficient sparse index). I compensated for the loss of semantic matching by building aggressive keyword "Intent Heuristics" (e.g., automatically boosting tests with the 'Leadership' tag if the query contains 'Manager'). This solved the OOM crash while preserving the high `Recall@10` evaluation metric.
2. **LLM URL Hallucinations:** Initially, the LLM consistently hallucinated fake catalog URLs or double-rendered them inside the conversational reply string. 
   - *Fix:* I built a strict `_guardrail_validate` function. It intercepts the LLM's raw output, verifies the suggested test name against the catalog JSON, drops any hallucinated items, and autonomously maps the correct URL from the database.
3. **Context Bloat:** Pushing 15 retrieved assessments into the prompt on every single stateless turn caused massive token bloat, leading to high latency and API rate-limiting.
   - *Fix:* I aggressively reduced the `top_k` threshold to 8, and stripped redundant URL data from the injected context string, reducing the prompt footprint by >60%.
4. **Cloud API Deprecations:** During deployment, both Google and Groq completely decommissioned the older model aliases (`gemini-1.5-flash` and `llama3-70b-8192`), causing the fallback cascade to fail simultaneously.
   - *Fix:* Shifted code defaults and cloud environment variables to point securely to `gemini-2.5-flash` and `llama-3.3-70b-versatile`.

## 6. AI Tools Disclosure
I utilized an advanced agentic AI coding assistant (Google DeepMind/Antigravity) as a pair-programmer. The AI was primarily used to rapidly scaffold the FastAPI boilerplate, implement the BM25/Semantic retrieval logic, write the robust Regex JSON parsers, and iteratively refactor code to ensure strict adherence to the assignment's schema constraints.
