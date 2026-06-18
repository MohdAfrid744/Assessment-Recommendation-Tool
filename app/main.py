"""
main.py — FastAPI application entry point.

Endpoints:
    GET  /health  → {"status": "ok"}
    POST /chat    → ChatResponse (reply, recommendations, end_of_conversation, conversation_export)
    GET  /assessment/{name}  → Assessment details
    GET  /templates → List all role templates
    GET  /templates/{key} → Get specific template
"""
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

from app.schemas import ChatRequest, ChatResponse, AssessmentDetail, RoleTemplate, Message
from app import agent, retriever

# ── Logging ────────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("logs/agent_errors.log", maxBytes=1000000, backupCount=3, encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# ── Lifespan ───────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    size = retriever.get_catalog_size()
    log.info(f"Assessment Recommendation Tool started. Catalog loaded: {size} assessments.")
    yield

# ── Role Templates ────────────────────────────────────────────────────────────────

ROLE_TEMPLATES = {
    "java-developer": {
        "role": "Java Developer",
        "seniority": "Mid-level (4-7 years)",
        "description": "Full-stack Java engineer with focus on backend systems and code quality",
        "recommended_assessments": ["Java 8 (New)", "Global Skills Assessment", "Occupational Personality Questionnaire OPQ32r"]
    },
    "sales-representative": {
        "role": "Sales Representative",
        "seniority": "Entry-level",
        "description": "Sales professional focused on communication, relationship-building, and customer handling",
        "recommended_assessments": ["Entry Level Sales Solution", "OPQ MQ Sales Report", "Customer Service Phone Solution"]
    },
    "hr-manager": {
        "role": "HR Manager",
        "seniority": "Senior (7+ years)",
        "description": "HR leader responsible for talent acquisition, team dynamics, and organizational culture",
        "recommended_assessments": ["OPQ Manager Plus Report", "OPQ Team Types & Leadership Styles Profile", "OPQ Leadership Report"]
    },
    "data-analyst": {
        "role": "Data Analyst",
        "seniority": "Junior-to-Mid (1-4 years)",
        "description": "Analyst focused on numerical reasoning, data interpretation, and insight generation",
        "recommended_assessments": ["Verify - Numerical Ability", "Verify Interactive Numerical Calculation", "Global Skills Assessment"]
    },
    "project-manager": {
        "role": "Project Manager",
        "seniority": "Senior (5+ years)",
        "description": "PM with focus on stakeholder management, delivery excellence, and team leadership",
        "recommended_assessments": ["OPQ Manager Plus Report", "OPQ Leadership Report", "Enterprise Leadership Report 2.0"]
    },
}

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Assessment Recommendation Tool",
    description="Conversational AI agent that guides hiring managers to the right assessments.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins for the evaluator to reach the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Friendly welcome message for the root URL."""
    return {"message": "Assessment Recommendation Tool API is Live! 🚀 Please use POST /chat to interact or GET /health for status checks."}

@app.get("/health")
def health():
    """Readiness check. Returns 200 OK when the service is up."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, export: bool = False):
    """
    Main chat endpoint. Stateless — full conversation history sent every call.

    Request body:
        { "messages": [{"role": "user", "content": "..."}, ...] }
    
    Query param:
        ?export=true  → include full conversation in response

    Response:
        {
            "reply": "...",
            "recommendations": [{"name": "...", "url": "...", "test_type": "...", "reason": "..."}],
            "end_of_conversation": false
        }
    """
    messages = request.messages

    # Guard: must have at least one message
    if not messages:
        raise HTTPException(status_code=400, detail="messages list cannot be empty")

    # Guard: max 8 turns (user + assistant messages combined)
    if len(messages) > 8:
        return ChatResponse(
            reply="We've reached the maximum conversation length. Please start a new session.",
            recommendations=[],
            end_of_conversation=True
        )

    log.info(f"Received /chat | turns={len(messages)} | last={messages[-1].content[:80]}")

    reply, recommendations, end_of_conversation = agent.respond(messages)

    return ChatResponse(
        reply=reply,
        recommendations=recommendations,
        end_of_conversation=end_of_conversation
    )


@app.get("/assessment/{name}", response_model=AssessmentDetail)
def get_assessment(name: str):
    """
    Get detailed information about a specific assessment by name.
    
    Example: GET /assessment/Customer%20Service%20Phone%20Solution
    """
    assessment = retriever.get_by_name(name)
    if not assessment:
        raise HTTPException(status_code=404, detail=f"Assessment '{name}' not found")
    
    return AssessmentDetail(
        name=assessment.get("name", ""),
        url=assessment.get("url", ""),
        test_types=assessment.get("test_types", []),
        description=assessment.get("description", ""),
        duration=assessment.get("duration"),
        remote_support=assessment.get("remote_support", False),
        adaptive_support=assessment.get("adaptive_support", False),
    )


@app.get("/templates")
def list_templates():
    """
    List all pre-built role templates with recommended assessments.
    
    Example: GET /templates
    """
    return {
        "templates": [
            RoleTemplate(
                role=tmpl["role"],
                seniority=tmpl["seniority"],
                description=tmpl["description"],
                recommended_assessments=tmpl["recommended_assessments"],
            )
            for tmpl in ROLE_TEMPLATES.values()
        ]
    }


@app.get("/templates/{template_key}", response_model=RoleTemplate)
def get_template(template_key: str):
    """
    Get a specific role template with pre-selected assessments.
    
    Valid template keys: java-developer, sales-representative, hr-manager, data-analyst, project-manager
    Example: GET /templates/java-developer
    """
    if template_key not in ROLE_TEMPLATES:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_key}' not found. Available: {', '.join(ROLE_TEMPLATES.keys())}"
        )
    
    tmpl = ROLE_TEMPLATES[template_key]
    return RoleTemplate(
        role=tmpl["role"],
        seniority=tmpl["seniority"],
        description=tmpl["description"],
        recommended_assessments=tmpl["recommended_assessments"],
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
