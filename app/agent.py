"""
agent.py — Slot-filling conversational agent with Dual-LLM support and Self-Critique Guardrails.

Flow per turn:
    1. Build a context string from the full conversation history
    2. Run the retriever to get top candidates
    3. Determine active provider (Gemini or Groq)
    4. Call LLM
    5. Pass output through Guardrail (hallucination prevention)
    6. Return response
"""

import os
import json
import logging
import re
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq

from app.schemas import Message, Recommendation
from app import retriever

load_dotenv()
log = logging.getLogger(__name__)

# Configure Gemini
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)

groq_client = Groq() if os.getenv("GROQ_API_KEY") else None

SYSTEM_PROMPT = """You are a consultative, highly professional Organizational Psychologist and Assessment Recommendation Agent. Your job is to help hiring managers choose the right assessments for their open roles based on scientific validity and catalog data. Maintain a sophisticated, authoritative, yet helpful tone.

## Rules:
1. CLARIFY: If vague (e.g., "hire python dev"), output empty `recommendations` and ask for seniority/purpose.
2. JDs: Extract seniority/purpose from pasted Job Descriptions. Don't ask redundant questions.
3. RECOMMEND: Give 1-10 tests ONLY when context is clear. Use CATALOG CANDIDATES below.
4. MISSING SKILLS: If requested skill (e.g. Python) isn't in CATALOG, suggest general cognitive/behavioral tests instead.
5. REFINE/COMPARE: Update shortlist if constraints change. Compare using ONLY catalog data.
6. REFUSE: Decline off-topic questions.

## Formatting:
- DO NOT list names/URLs in `reply`. The UI renders them. Keep `reply` under 2 sentences.

## Few-Shot Examples:
User: "test for data analyst"
Output: {"reply": "Is this for entry-level or senior? Selection or development?", "recommendations": [], "end_of_conversation": false}

User: "Entry-level selection"
Output: {"reply": "Here are validated options:", "recommendations": [{"name": "Verify - Numerical Ability", "test_type": "Ability & Aptitude", "job_levels": ["Entry-Level"], "languages": ["English"], "reason": "Measures numerical reasoning."}], "end_of_conversation": true}

## Output format (strict JSON, no markdown formatting blocks around it):

{
  "reply": "Short natural response",
  "recommendations": [
    {
      "name": "Exact Name", 
      "test_type": "Key", 
      "job_levels": ["Level"], 
      "languages": ["Lang"], 
      "reason": "Short reason"
    }
  ],
  "end_of_conversation": false
}

- "recommendations" must have 1–10 items when recommending.
- "end_of_conversation" is true ONLY when user agrees on a final shortlist.
- Omit URL, the system injects it automatically.

## CATALOG CANDIDATES:
{catalog_section}

Respond ONLY with the raw JSON object. Do not wrap in ```json ``` blocks.
"""


def _build_catalog_section(candidates: List[dict]) -> str:
    """Format retrieved candidates for the system prompt."""
    if not candidates:
        return "No candidates retrieved. Ask clarifying questions."

    lines = []
    for c in candidates:
        keys = ",".join(c.get("keys", []))
        levels = ",".join(c.get("job_levels", []))
        dur = f"{c.get('duration', 'untimed')}"
        lines.append(
            f"- {c.get('name', '')} | keys={keys} | levels={levels} | remote={c.get('remote', 'no')}\n"
            f"  desc: {c.get('description','')[:80]}..."
        )
    return "\n\n".join(lines)


def _extract_query_from_history(messages: List[Message]) -> str:
    user_texts = [m.content for m in messages if m.role == "user"]
    return " ".join(user_texts)


def _detect_refine_intent(messages: List[Message]) -> bool:
    if len(messages) < 2: return False
    last_user_msg = next((m.content.lower() for m in reversed(messages) if m.role == "user"), "")
    refine_keywords = ["add", "remove", "only", "instead", "also", "too", "include", "exclude", "but not"]
    return any(k in last_user_msg for k in refine_keywords)


def _detect_compare_intent(messages: List[Message]) -> bool:
    if len(messages) < 2: return False
    last_user_msg = next((m.content.lower() for m in reversed(messages) if m.role == "user"), "")
    compare_keywords = ["difference", "compare", "vs", "versus", "better than", "worse than"]
    return any(k in last_user_msg for k in compare_keywords)


def _call_gemini(system: str, messages: List[Message]) -> str:
    model_name = os.getenv("GEMINI_MODEL")
    if not model_name:
        raise ValueError("GEMINI_MODEL environment variable must be set (e.g., gemini-2.5-flash)")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system,
        generation_config={"response_mime_type": "application/json", "temperature": 0.1}
    )
    
    gemini_messages = []
    for m in messages:
        role = "model" if m.role == "assistant" else "user"
        gemini_messages.append({"role": role, "parts": [m.content]})
        
    response = model.generate_content(gemini_messages)
    return response.text

def _call_groq(system: str, messages: List[Message]) -> str:
    if not groq_client:
        raise ValueError("GROQ_API_KEY not found in environment.")
        
    model = os.getenv("GROQ_MODEL")
    if not model:
        raise ValueError("GROQ_MODEL environment variable must be set (e.g., llama-3.3-70b-versatile)")
    payload_messages = [{"role": "system", "content": system}]
    payload_messages.extend([{"role": m.role, "content": m.content} for m in messages])
    
    chat_completion = groq_client.chat.completions.create(
        messages=payload_messages,
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"}
    )
    return chat_completion.choices[0].message.content


def _guardrail_validate(recommendations: List[dict]) -> List[Recommendation]:
    """
    Self-critique loop: Ensures LLM didn't hallucinate names/URLs.
    Re-maps URLs from exact catalog if name partially matches.
    """
    valid_recs = []
    for r in recommendations:
        if not isinstance(r, dict):
            continue
        name = r.get("name", "")
        # Lookup actual catalog item
        real_item = retriever.get_by_name(name)
        if real_item:
            # Safely extract types to prevent Pydantic ValidationErrors
            raw_levels = r.get("job_levels")
            levels = raw_levels if isinstance(raw_levels, list) else real_item.get("job_levels", [])
            
            raw_langs = r.get("languages")
            langs = raw_langs if isinstance(raw_langs, list) else real_item.get("languages", [])
            
            test_type = str(r.get("test_type", "")) or ", ".join(real_item.get("keys", []))
            
            try:
                valid_recs.append(Recommendation(
                    name=real_item.get("name"),
                    url=str(real_item.get("link", "")),
                    test_type=test_type,
                    job_levels=levels,
                    languages=langs,
                    reason=str(r.get("reason", "Highly relevant to requested competencies."))
                ))
            except Exception as e:
                log.warning(f"Guardrail dropped item due to Pydantic validation: {e}")
        else:
            log.warning(f"Guardrail dropped hallucinated assessment: {name}")
    return valid_recs


def _parse_llm_output(raw: str) -> Tuple[str, List[Recommendation], bool]:
    data = {}
    try:
        # Failsafe 1: strip markdown blocks
        clean_raw = raw.replace("```json", "").replace("```", "").strip()
        
        # Failsafe 2: regex extract JSON object in case of conversational padding
        match = re.search(r'\{.*\}', clean_raw, re.DOTALL)
        if match:
            clean_raw = match.group(0)
            
        data = json.loads(clean_raw)
    except json.JSONDecodeError as e:
        log.error(f"JSON Decode Error: {e} | Raw string: {raw}")
        return ("I'm having trouble formulating my response. Could you rephrase?", [], False)

    reply = data.get("reply", "I'm sorry, I encountered an issue. Could you rephrase?")
    end_of_conversation = bool(data.get("end_of_conversation", False))
    raw_recs = data.get("recommendations", [])
    
    # Run through guardrail
    recommendations = _guardrail_validate(raw_recs)

    return reply, recommendations, end_of_conversation


# ── Public API ─────────────────────────────────────────────────────────────────

def respond(messages: List[Message]) -> Tuple[str, List[Recommendation], bool]:
    query = _extract_query_from_history(messages)
    is_refine = _detect_refine_intent(messages)
    is_compare = _detect_compare_intent(messages)
    
    # Dynamic Slot-Mapping implicitly handled by new Retriever architecture
    candidates = retriever.search(query, top_k=8)
    catalog_section = _build_catalog_section(candidates)
    
    system = SYSTEM_PROMPT.replace("{catalog_section}", catalog_section)
    if is_refine:
        system += "\n\nIMPORTANT: The user is refining requirements. Update the assessment shortlist based on new constraints."
    elif is_compare:
        system += "\n\nIMPORTANT: The user is asking for a comparison. Use only catalog data to provide factual differences."

    try:
        raw_response = _call_gemini(system, messages)
        provider = "Gemini"
        log.debug(f"[Gemini] Raw Output: {raw_response}")
    except Exception as gemini_err:
        log.warning(f"Gemini failed: {gemini_err}. Cascading to Groq...")
        try:
            raw_response = _call_groq(system, messages)
            provider = "Groq"
            log.debug(f"[Groq] Raw Output: {raw_response}")
        except Exception as groq_err:
            log.error(f"Both Gemini and Groq failed. Groq Error: {groq_err}")
            return ("I'm experiencing a technical issue. Please try again in a moment.", [], False)
            
    reply, recs, eoc = _parse_llm_output(raw_response)
    
    # Safely append provider info to the reply string to avoid schema deviation
    reply += f"\n\n*(Responded via {provider})*"
    
    return reply, recs, eoc
