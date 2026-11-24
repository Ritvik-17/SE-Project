import { useEffect, useState } from "react";
import { api } from "../api";
import Diagram from "../components/Diagram";

const AGENTS: [string, string, string][] = [
  ["Coordinator", "intake · consolidate · all routing", "Loads masked sources, fans out extraction per chunk, merges and numbers requirements, decides every next step with deterministic rules."],
  ["Stakeholder interaction", "separate interview graph", "Adaptive interview over the 13 step-7 topics relevant to the role; assesses every answer and follows up on incomplete, vague or inconsistent ones; saves transcript, coverage and open points as a source."],
  ["Requirement extraction", "extraction (parallel)", "Extracts atomic, testable requirements in the step-8 structure: statement, categories, priority, justification, assumptions, dependencies, acceptance criteria and a verbatim source quote."],
  ["Classification", "classification", "Makes FR/NFR type, 13-category multi-label tags (never empty) and MoSCoW priority consistent across sources, and links dependencies between requirements."],
  ["Clarification", "clarification (after validation)", "Receives every requirement that failed a quality check and asks a question for each, plus domain gaps, routed to the role best placed to answer. Failures of blocking checks pause the graph at the clarification gate."],
  ["Quality review", "quality_review ∥", "Semantic step-10 checks: ambiguity, incompleteness, infeasibility and lack of testability, each with a concrete fix."],
  ["Conflict detection", "conflict_detection ∥", "Finds contradictions, duplicates and overlaps between requirements and stakeholders."],
  ["Compliance", "compliance ∥", "Proposes, never decides: maps requirements to regulations with jurisdiction, required controls, KB evidence, retention/reporting obligations and mandatory checkpoints; lists gaps. High-impact or weakly evidenced mappings need compliance/legal approval."],
  ["Security & privacy", "security_privacy ∥", "Finds missing controls, weak security requirements and privacy risks, and proposes requirements."],
  ["Risk analysis", "risk_analysis ∥", "Builds the risk register: business, technical, compliance, security and operational risks, with likelihood × impact."],
  ["Grounding", "grounding ∥", "Step 6 for every requirement: retrieves the policies and regulations its categories call for, judges whether it is supported or contradicts them, attaches verified citations and a combined confidence, and escalates the rest to human review."],
  ["Validation", "validation (join)", "Runs the ten step-10 quality checks (missing source verified against the source text), completes each requirement's regulations and risk level, scores quality and returns failing requirements to the clarification agent."],
  ["Human approval", "clarification_gate · baseline_approval · sdlc_approval · workflow_approval", "Decides who must approve and pauses the graph. Requirements that are high-risk security, architecture-critical, in stakeholder conflict or escalated must be accepted, modified or rejected by the role that owns them; compliance decides every regulatory interpretation. After completion, change requests and production-readiness reviews keep humans in control."],
  ["SDLC selection", "sdlc_selection", "Derives all 13 step-13 decision factors (system size and stakeholder availability measured from project data). It answers the course's 19 SDLC-selection questions (approvers can correct them), then TOPSIS, weighted fit and 30 sourced rules (problem statement, course slides, research) rank 10 models by % suitability; the LLM explains the ranking."],
  ["Workflow", "sdlc_workflow", "Customises the approved model: fills each canonical phase with project-specific activities, roles, deliverables, security, testing, compliance checkpoints, approval gates, entry/exit criteria and traceability; schedules the timeline from the model's structure (sequential, V-paired, sprints, cycles, continuous pipeline) and enforces mandatory controls in the right phase."],
  ["Documentation", "persist_baseline · documentation", "Saves the baseline and generates the eleven step-12 artefacts, from the SRS to the assumptions and dependency register; every row links to its stakeholder statement and supporting document."],
];

export default function AgentsPage() {
  const [graphs, setGraphs] = useState<{ analysis: string; interview: string } | null>(null);
  useEffect(() => {
    api.graph().then(setGraphs);
  }, []);

  return (
    <main className="page">
      <header className="page-head">
      <span className="eyebrow">Step 4 · multi-agent architecture</span>
      <h1>Agent graph</h1>
      <p className="muted">
        Rendered live from the compiled LangGraph objects. Solid arrows are fixed edges; dotted arrows are routing decisions made by the coordinator.
        The six analysis agents run in parallel and join at validation.
      </p>
      </header>
      <section className="card">
        <h2>Requirements-analysis graph</h2>
        {graphs ? <Diagram code={graphs.analysis} /> : <p className="muted">Loading…</p>}
      </section>
      <div className="two-col">
        <section className="card">
          <h2>Interview graph</h2>
          {graphs && <Diagram code={graphs.interview} />}
        </section>
        <section className="card">
          <h2>Human gates</h2>
          <ul className="small">
            <li><strong>Clarification:</strong> blocking questions are routed to stakeholder roles. Answers become sources and the agents re-run (at most 2 rounds).</li>
            <li><strong>Baseline approval:</strong> the product owner always approves. Compliance approves if there are regulatory items or legal-review flags, infosec if there are high-severity security issues, and the architect if there are must-have integration or performance requirements.</li>
            <li><strong>SDLC approval:</strong> product owner, architect, infosec and compliance.</li>
            <li>Every gate supports approve, regenerate with feedback, and per-item edits. All decisions are audited.</li>
          </ul>
        </section>
      </div>
      <section className="section">
        <h2>Agents</h2>
        <table>
          <thead><tr><th>Agent</th><th>Graph node(s)</th><th>Responsibility</th></tr></thead>
          <tbody>{AGENTS.map(([a, n, d]) => <tr key={a}><td><strong>{a}</strong></td><td><code>{n}</code></td><td>{d}</td></tr>)}</tbody>
        </table>
      </section>
    </main>
  );
}
