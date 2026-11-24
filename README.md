# Financial Requirements Engineering Agent

A multi-agent system (LangGraph + OpenAI) that gathers and analyses requirements for financial-sector software
and recommends an SDLC model. It includes masking of sensitive data, human approval gates and an audit trail.

- **Architecture:** [guide/architecture.md](guide/architecture.md)
- **Which stakeholder supplies which requirements:** [guide/requirement_role_mapping.md](guide/requirement_role_mapping.md)
- **Knowledge base (structure, chunking, retrieval, updates):** [guide/knowledge_base.md](guide/knowledge_base.md)
- **Retrieval-grounded generation (step 6):** [guide/retrieval_grounded_generation.md](guide/retrieval_grounded_generation.md)
- **Adaptive requirement-gathering interviews (step 7):** [guide/adaptive_interviews.md](guide/adaptive_interviews.md)
- **Agent standards (steps 8–13):** [guide/agent_standards.md](guide/agent_standards.md)
- **SDLC selection research & rules (step 14):** [guide/sdlc_selection_research_and_rules.md](guide/sdlc_selection_research_and_rules.md)
- **Project-specific SDLC workflow (step 15):** [guide/sdlc_workflow_generation.md](guide/sdlc_workflow_generation.md)
- **Human in the loop (step 16):** [guide/human_in_the_loop.md](guide/human_in_the_loop.md)
- **Platform security (step 17):** [guide/platform_security.md](guide/platform_security.md)
- **Technology stack (step 18):** [guide/architecture.md §1.1](guide/architecture.md#11-prototype-technology-stack-step-18)
- **Testing and evaluation, with the full loan-case testing flow (step 19):** [guide/evaluation.md](guide/evaluation.md)
- **Deploy, monitor and improve (step 20):** [guide/deployment_and_monitoring.md](guide/deployment_and_monitoring.md)

Stack: React + Vite (frontend) · FastAPI + LangGraph (backend) · OpenAI · PostgreSQL + pgvector (Docker, TLS) · Presidio ·
built-in IAM (RBAC + TOTP MFA) · AES-256-GCM encryption at rest

## One-time setup

```powershell
docker compose up -d                                   # Postgres 16 + pgvector on :5432 (TLS-only TCP)
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m spacy download en_core_web_sm  # NER model for masking
copy .env.example .env                                 # then set OPENAI_API_KEY
.venv\Scripts\python -m app.security.crypto           # prints DATA_ENCRYPTION_KEY=... → put it in .env (required)
cd frontend; npm install; cd ..
.venv\Scripts\python -m app.kb.seed --approve-as compliance_legal   # seed the knowledge base; local bge-small embeddings, no key needed
.venv\Scripts\python -m app.kb.seed --embed                         # only if passages were stored without vectors
.venv\Scripts\python -m app.security.users create admin --roles admin,project_manager   # first account; prints a one-time password
```

At first sign-in each user enrols an authenticator app (MFA is mandatory) and should change the one-time password.
Administrators then create other users and assign roles under **Administration**; project creators add members.

## Run (three terminals, from Code/)

```powershell
docker compose up -d                                   # 1. database (if not already running)
.venv\Scripts\uvicorn app.api.main:app --reload        # 2. API  → http://localhost:8000/docs
cd frontend; npm run dev                               # 3. UI   → http://localhost:5173 (sign in)
```

HTTPS end to end (optional in development, always in production):

```powershell
.venv\Scripts\python -m app.security.devcert          # certs/localhost.pem (self-signed; trust it locally)
.venv\Scripts\uvicorn app.api.main:app --reload --ssl-certfile certs/localhost.pem --ssl-keyfile certs/localhost-key.pem
cd frontend; $env:RERA_HTTPS="1"; npm run dev          # https://localhost:5173 → https://localhost:8000
```

## Other commands

```powershell
.venv\Scripts\pytest                                   # tests (LLM stubbed; needs the DB container)
.venv\Scripts\python -m app.catalog.render_guide       # regenerate the role-mapping guide after editing the catalog YAML
.venv\Scripts\python -m app.security.retention        # retention dry run (--apply to purge)
.venv\Scripts\python -m app.security.crypto --reencrypt  # after a key rotation
.venv\Scripts\python -m app.security.users list       # accounts; also reset-mfa / unlock <username>
docker compose down -v                                 # wipe the database
.venv\Scripts\python -m eval.run --case loan_digital_lending              # automated evaluation (real model calls, metered)
.venv\Scripts\python -m eval.run --case loan_digital_lending --project 7  # score a project you reviewed in the UI
.venv\Scripts\python -m eval.sdlc_benchmark                               # SDLC engine vs expert labels (no model calls)
```

New installations start in **advisory mode** (step 20): outputs are watermarked and compared with the business analysts'
work until an evaluation passes and an administrator moves the system to assisted under **Deployment & monitoring**.
