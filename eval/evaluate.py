import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def load_traces(path: Path) -> List[Dict[str, Any]]:
    traces: List[Dict[str, Any]] = []
    if path.is_file():
        traces.append(_load_json(path))
    else:
        for child in sorted(path.glob("*.json")):
            traces.append(_load_json(child))
    return traces


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    return name.strip().lower()


class LocalChatClient:
    def __init__(self, app):
        from fastapi.testclient import TestClient

        self.client = TestClient(app)

    def chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        response = self.client.post("/chat", json={"messages": messages})
        response.raise_for_status()
        return response.json()


class RemoteChatClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        import urllib.request

        body = json.dumps({"messages": messages}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)


def build_client(endpoint: Optional[str]) -> Any:
    if endpoint:
        return RemoteChatClient(endpoint)

    import sys

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from app.main import app

    return LocalChatClient(app)


def compute_recall_at_k(
    recommended: List[Dict[str, Any]],
    relevant: Iterable[str],
    k: int = 10,
) -> float:
    relevant_set = {normalize_name(name) for name in relevant}
    if not relevant_set:
        return 0.0

    recommended_names = [normalize_name(rec.get("name", "")) for rec in recommended[:k]]
    hits = sum(1 for name in recommended_names if name in relevant_set)
    return hits / len(relevant_set)


def evaluate_trace(trace: Dict[str, Any], client: Any) -> Dict[str, Any]:
    conversation = trace.get("conversation") or trace.get("messages") or []
    relevant = trace.get("relevant", [])
    if not conversation:
        raise ValueError("Trace must contain 'conversation' or 'messages'.")

    response = client.chat(conversation)
    recall = compute_recall_at_k(response.get("recommendations", []), relevant)
    return {
        "id": trace.get("id", trace.get("name", "unknown")),
        "status_code": response.get("status_code", 200),
        "reply": response.get("reply", ""),
        "recommendation_count": len(response.get("recommendations", [])),
        "recall_at_10": recall,
        "end_of_conversation": response.get("end_of_conversation", False),
        "recommendations": response.get("recommendations", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Assessment Recommendation Tool /chat recall against labeled traces.")
    parser.add_argument("--traces", type=str, default="eval/traces", help="Path to trace JSON file or directory.")
    parser.add_argument("--endpoint", type=str, default=None, help="Optional hosted /chat base URL. If omitted, evaluates locally.")
    parser.add_argument("--output", type=str, default=None, help="Optional JSON file to write evaluation results.")
    args = parser.parse_args()

    traces_path = Path(args.traces)
    if not traces_path.exists():
        raise FileNotFoundError(f"Traces path not found: {traces_path}")

    traces = load_traces(traces_path)
    if not traces:
        raise ValueError(f"No trace files found in {traces_path}")

    client = build_client(args.endpoint)
    results = []
    for trace in traces:
        print(f"Evaluating trace: {trace.get('id', trace.get('name', 'unknown'))}")
        result = evaluate_trace(trace, client)
        results.append(result)
        print(f"  Recall@10: {result['recall_at_10']:.2f}, recommendations: {result['recommendation_count']}")
        print(f"  Recommendation names: {[rec.get('name') for rec in result['recommendations']]}")

    mean_recall = sum(r["recall_at_10"] for r in results) / len(results)
    print("\nSummary")
    print(f"  Traces evaluated: {len(results)}")
    print(f"  Mean Recall@10: {mean_recall:.4f}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"results": results, "mean_recall_at_10": mean_recall}, f, indent=2)
        print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
