"""
retriever.py — Advanced Sparse Retriever with Intent Heuristics.

This implementation uses BM25Okapi for keyword relevance, heavily augmented 
by custom heuristic slot-mapping to handle intent detection without requiring
heavy Neural Network embeddings that crash 512MB cloud instances.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

# Load catalog once at import time
_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "shl_catalogue_json.json")


def _load_catalog() -> List[Dict[str, Any]]:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)

CATALOG = _load_catalog()


def _tokenize(text: str) -> List[str]:
    """Lowercase, remove punctuation, split into words, drop short words."""
    if not text:
        return []
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [w for w in text.split() if len(w) > 2]


def _build_documents(catalog: List[Dict[str, Any]]) -> List[List[str]]:
    documents = []
    for assessment in catalog:
        parts = [
            assessment.get("name", ""),
            assessment.get("description", ""),
            " ".join(assessment.get("keys", [])),
            " ".join(assessment.get("job_levels", []))
        ]
        documents.append(_tokenize(" ".join(parts)))
    return documents


def _candidate_text(candidate: Dict[str, Any]) -> str:
    return f"{candidate.get('name', '')} {candidate.get('description', '')}".lower()


def _extract_query_terms(query: str) -> set[str]:
    return set(_tokenize(query))


def _exact_match_boost(candidate_text: str, query_terms: set[str]) -> float:
    match_count = sum(1 for term in query_terms if term in candidate_text)
    return match_count * 1.5  # Scaled up for BM25 float distribution


# High-value keywords for dynamic slot-mapping / heuristics
BEHAVIORAL_QUERY = "teamwork collaboration behavioral assessment personality interpersonal communication leadership"
TECHNICAL_TERMS = {
    "developer", "engineer", "java", "python", "sql", "software", "backend", "frontend",
    "cloud", "aws", "azure", "devops", "data", "react", "angular", "node", "spring", "coding", "programming"
}
BEHAVIORAL_TERMS = {
    "teamwork", "collaboration", "behavioral", "personality", "leadership", "communication",
    "interpersonal", "motivation", "soft skills", "culture", "empathy",
}

REMOTE_TERMS = {"remote", "distributed", "virtual", "work from home", "hybrid"}
MANAGER_TERMS = {"manager", "lead", "leader", "supervisor", "director", "head", "vp", "project manager", "product manager", "executive", "cxo", "c-level"}


def _is_behavioral_query(query: str) -> bool:
    lower = query.lower()
    return any(term in lower for term in BEHAVIORAL_TERMS)


def _is_technical_query(query: str) -> bool:
    lower = query.lower()
    return any(term in lower for term in TECHNICAL_TERMS)


def _is_manager_query(query: str) -> bool:
    lower = query.lower()
    return any(term in lower for term in MANAGER_TERMS)


def _type_filtered_indices(catalog: List[Dict[str, Any]], required_keys: List[str]) -> List[int]:
    indices = []
    for idx, assessment in enumerate(catalog):
        keys = assessment.get("keys", [])
        if any(t in keys for t in required_keys):
            indices.append(idx)
    return indices


class AdvancedSparseRetriever:
    def __init__(self, catalog: List[Dict[str, Any]]):
        self.catalog = catalog
        self.documents = _build_documents(catalog)
        self.bm25 = BM25Okapi(self.documents)

    def search(
        self,
        query: str,
        top_k: int = 30,
        filter_keys: Optional[List[str]] = None,
        filter_levels: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not query.strip():
            return []

        query_tokens = _tokenize(query)
        bm25_scores = self.bm25.get_scores(query_tokens)

        filtered_indices = []
        for idx, assessment in enumerate(self.catalog):
            if filter_keys:
                keys = assessment.get("keys", [])
                if not any(k in keys for k in filter_keys):
                    continue
            if filter_levels:
                levels = assessment.get("job_levels", [])
                if levels and not any(lvl in levels for lvl in filter_levels):
                    continue
            filtered_indices.append(idx)

        if not filtered_indices:
            return []

        ranked_scores: Dict[int, float] = {}
        query_lower = query.lower()
        query_terms = _extract_query_terms(query)
        is_manager = _is_manager_query(query)

        # Baseline BM25 Assignment
        for idx in filtered_indices:
            ranked_scores[idx] = float(bm25_scores[idx])

        # Apply Intent Heuristics
        for idx in filtered_indices:
            assessment = self.catalog[idx]
            candidate_text = _candidate_text(assessment)
            
            boost = _exact_match_boost(candidate_text, query_terms)
            
            if any(term in query_lower for term in REMOTE_TERMS) and assessment.get("remote") == "yes":
                boost += 3.0
            
            # Explicitly boost Leadership tests for managerial roles
            if is_manager:
                levels = assessment.get("job_levels", [])
                if any(lvl in levels for lvl in ["Manager", "Director", "Executive", "Supervisor", "Front Line Manager"]):
                    boost += 8.0
                if "Personality & Behavior" in assessment.get("keys", []):
                    boost += 5.0
                    
            ranked_scores[idx] += boost

        # Behavioral Fast-Path
        if _is_behavioral_query(query):
            behavior_tokens = _tokenize(BEHAVIORAL_QUERY)
            behavior_bm25_scores = self.bm25.get_scores(behavior_tokens)
            behavior_indices = _type_filtered_indices(self.catalog, ["Personality & Behavior", "Competencies"])
            for idx in behavior_indices:
                if idx in filtered_indices:
                    ranked_scores[idx] += float(behavior_bm25_scores[idx]) * 0.8

        # Technical Fast-Path
        if _is_technical_query(query):
            technical_indices = _type_filtered_indices(self.catalog, ["Ability & Aptitude", "Assessment Exercises", "Knowledge"])
            technical_tokens = _tokenize(query)
            technical_bm25_scores = self.bm25.get_scores(technical_tokens)
            for idx in technical_indices:
                if idx in filtered_indices:
                    ranked_scores[idx] += float(technical_bm25_scores[idx]) * 2.0

        sorted_indices = sorted(ranked_scores.keys(), key=lambda idx: ranked_scores[idx], reverse=True)
        return [self.catalog[idx] for idx in sorted_indices[:top_k]]


# Build retriever once at import time
RETRIEVER = AdvancedSparseRetriever(CATALOG)


def search(
    query: str,
    top_k: int = 20,
    filter_keys: Optional[List[str]] = None,
    filter_levels: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    return RETRIEVER.search(query, top_k=top_k, filter_keys=filter_keys, filter_levels=filter_levels)


def get_by_name(name: str) -> Optional[Dict[str, Any]]:
    name_lower = name.lower()
    for assessment in CATALOG:
        if name_lower in assessment["name"].lower():
            return assessment
    return None


def get_catalog_size() -> int:
    return len(CATALOG)
