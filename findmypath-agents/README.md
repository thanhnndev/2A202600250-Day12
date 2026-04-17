# Smart Apply Agents

LangGraph-powered school recommendation agent service for PathCan Academy.

## Features

- 🤖 **LangGraph State Machine**: Multi-agent workflow with profile collection, school search, and document generation
- 📄 **PDF Generation**: Professional recommendation documents with school details and QR codes
- 🔌 **Go Backend Integration**: Direct API calls to PathCan Go server (no external SmartApply API needed)
- 💬 **Streaming Support**: Real-time agent responses via SSE
- 🌍 **i18n Ready**: Support for English and Vietnamese

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│  Go Server       │────▶│ Python Agents   │
│   (React/Next)  │◀────│  (Echo v4)       │◀────│ (LangGraph)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                      │
                                                      ▼
                                              ┌─────────────────┐
                                              │  Go Backend     │
                                              │  SmartApply APIs│
                                              └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Go 1.25+
- Docker (optional)

### Local Development

1. **Clone and setup:**
```bash
cd findmypath-agents
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

If `uvicorn` fails with an interpreter path from another folder (e.g. `smartapply-agents`), the venv was copied or broken — remove `venv` and recreate it with the commands above.

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Run the service** (from `findmypath-agents`, with the venv activated):
```bash
python -m src.main
# Or with uvicorn:
uvicorn src.main:app --reload --host 0.0.0.0 --port 18000
```

Use `python -m src.main` (not `python src/main.py`) so imports like `from src.graph...` resolve. Alternatively set `PYTHONPATH=.` when running `python src/main.py`.

4. **Test the agent:**
```bash
python tests/test_e2e.py
```

5. **Access Swagger docs:**
```
http://localhost:18000/docs
```

### Test Results

```bash
$ python tests/test_e2e.py

🧪 Smart Apply Agents - End-to-End Test Suite
======================================================================
✅ PASS - agent_graph
✅ PASS - complete_flow

Total: 2/2 tests passed
🎉 End-to-End Test PASSED!
```

### Docker Deployment

```bash
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/agents/chat` | Chat with agent (JSON response) |
| POST | `/api/v1/agents/chat/stream` | Chat with agent (SSE streaming) |

## Agent Workflow

```
[START]
   ↓
┌─────────────────────┐
│ Profile Collector   │ → Ask user questions (GPA, budget, countries, etc.)
└─────────────────────┘
   ↓
┌─────────────────────┐
│ School Finder       │ → Search Go backend APIs, rank by match score
└─────────────────────┘
   ↓
┌─────────────────────┐
│ Human Approval      │ → Show top 3 schools, get user confirmation
└─────────────────────┘
   ↓ (approved)
┌─────────────────────┐
│ Document Generator  │ → Create PDF recommendation document
└─────────────────────┘
   ↓
[END] → Email PDF to user
```

## Project Structure

```
smartapply-agents/
├── src/
│   ├── graph/
│   │   ├── state.py      # TypedDict schemas
│   │   ├── nodes.py      # Agent node implementations
│   │   └── graph.py      # LangGraph state graph wiring
│   ├── tools/
│   │   ├── go_api_client.py  # HTTP client for Go backend
│   │   └── school_tools.py   # School search tools
│   ├── templates/
│   │   └── recommendation.html  # Jinja2 PDF template
│   └── main.py           # FastAPI entry point
├── tests/
│   ├── test_nodes.py
│   ├── test_tools.py
│   └── test_graph.py
├── output/
│   └── pdfs/             # Generated PDFs
├── requirements.txt
├── .env.example
├── Dockerfile
└── README.md
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4-turbo-preview` |
| `GO_BACKEND_URL` | PathCan Go server URL | `http://localhost:8080` |
| `MAX_STEPS` | Maximum agent steps | `10` |
| `PDF_OUTPUT_DIR` | PDF output directory | `./output/pdfs` |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_graph.py -v
```

## Integration with Go Backend

The Python agent service calls Go backend APIs for school data:

```python
# Example: Search schools
from src.tools.go_api_client import GoAPIClient

client = GoAPIClient(base_url=os.getenv("GO_BACKEND_URL"))
schools = client.search_schools(country="USA", gpa=3.5, budget=30000)
```

Go handler example:

```go
// Go: POST /api/v1/agents/consult
func (h *SmartApplyAgentHandler) ConsultAgent(w http.ResponseWriter, r *http.Request) {
    // Call Python service
    resp, err := h.agentClient.Chat(ctx, request)
    // Stream response to frontend
}
```

## License

Proprietary - PathCan Academy
