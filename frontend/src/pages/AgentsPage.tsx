import { useEffect, useState } from "react";
import { api } from "../api";
import Diagram from "../components/Diagram";

interface AgentRow { name: string; ai: string; nodes: string; does: string[] }

const AGENTS: AgentRow[] = [
  {
    name: "Coordinator", ai: "No", nodes: "intake · consolidate · assess · requirements_gate · plan_gate",
    does: [
      "Loads the masked sources, splits them into chunks and sends one chunk to each extraction run.",
      "Merges the extraction results, removes exact repeats and records where each requirement came from.",
      "Scores the run: combines the review and compliance & security findings, runs the ten deterministic quality checks and calculates the quality scores.",
      "Makes sure every requirement that still fails a check has a stakeholder question.",
      "Runs both human approval gates and decides every next step with fixed rules, so runs are reproducible.",
    ],
  },
  {
    name: "Extraction", ai: "Yes", nodes: "extraction (one per chunk, in parallel)",
    does: [
      "Reads one chunk of one source and pulls out atomic, testable requirements (\"The system shall …\").",
      "Records a verbatim source quote, acceptance criteria, justification, assumptions, dependencies and a confidence score for each.",
      "Instruction-like text in a source (prompt injection) is removed before the model sees it.",
    ],
  },
  {
    name: "Classification", ai: "Yes", nodes: "classification",
    does: [
      "Decides whether each requirement is functional (something the system does) or non-functional (a quality, constraint or obligation).",
      "Assigns one or more of the 13 categories and a MoSCoW priority, consistently across all sources.",
      "Links dependencies between requirements and numbers them FR-… / NFR-… to match their final type.",
    ],
  },
  {
    name: "Review", ai: "Yes", nodes: "review (quality · conflicts · risk in parallel, then questions)",
    does: [
      "Quality: vague, incomplete, infeasible or untestable requirements, each with a concrete fix.",
      "Conflicts: contradictions, duplicates and overlaps between requirements and between stakeholders.",
      "Risk: a risk register with likelihood × impact, mitigation and linked requirements.",
      "Questions: drafts a question for each problem, routed to the stakeholder best placed to answer, marked blocking or not.",
    ],
  },
  {
    name: "Compliance & security", ai: "Yes", nodes: "compliance_security (three steps in parallel)",
    does: [
      "Compliance: maps requirements to regulations and obligations from the knowledge base and lists gaps. It proposes; compliance & legal decide.",
      "Security & privacy: missing controls, weak security requirements and privacy risks, with proposed requirements.",
      "Evidence: checks each requirement against approved policy, attaches citations and escalates weakly supported or contradicted ones to people.",
    ],
  },
  {
    name: "Planning", ai: "Yes (with a rules engine)", nodes: "planning",
    does: [
      "SDLC model: the rules engine and TOPSIS rank 10 models from 13 project factors and the course's selection questions; the model explains the ranking.",
      "Workflow: customises the chosen model's phases, roles, deliverables, compliance checkpoints and schedule, and enforces mandatory controls.",
      "If approvers pick a different model, or ask for a new workflow, only the workflow is rebuilt.",
    ],
  },
  {
    name: "Documentation", ai: "Yes", nodes: "freeze_baseline · documentation",
    does: [
      "Freezes the approved requirement baseline; after that it only changes through a change request.",
      "Generates the final documents (SRS, user stories, use cases, traceability matrix, compliance mapping and more), each linked back to its stakeholder statement.",
    ],
  },
];

const STEPS: [string, string][] = [
  ["Coordinator", "Loads the project's masked inputs and splits them into chunks."],
  ["Extraction ×N", "All chunks are read in parallel; each returns candidate requirements with a source quote."],
  ["Coordinator", "Merges the results and records where each requirement came from."],
  ["Classification", "Labels every requirement functional or non-functional, with categories and priority, and numbers them."],
  ["Review ∥ Compliance & security", "Run at the same time: quality, conflicts, risk and questions; regulations, security and evidence."],
  ["Coordinator", "Combines both reports, runs the quality checks, scores the run and finalises the questions."],
  ["⏸ Approve requirements", "Step 1: answer any blocking questions (answers re-run the analysis). Step 2: every required role signs off the baseline."],
  ["Documentation", "Freezes the approved baseline."],
  ["Planning", "Recommends the SDLC model and builds the project workflow for it."],
  ["⏸ Approve plan", "Step 1: approve the SDLC model. Step 2: approve the workflow."],
  ["Documentation", "Generates the final documents. Done."],
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
          Seven agents analyse the inputs, with two points where people must approve before the flow continues.
          The diagram is drawn live from the compiled LangGraph: solid arrows are fixed steps, dotted arrows are routing
          decisions made by the coordinator.
        </p>
      </header>

      <section className="card">
        <h2>Requirements-analysis graph</h2>
        {graphs ? <Diagram code={graphs.analysis} /> : <p className="muted">Loading…</p>}
      </section>

      <section className="section">
        <h2>The flow, start to end</h2>
        <ol className="stack tight">
          {STEPS.map(([who, what], i) => (
            <li key={i}><strong>{who}</strong> · <span className="muted">{what}</span></li>
          ))}
        </ol>
      </section>

      <section className="section">
        <h2>The seven agents</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Agent</th><th>Uses AI</th><th>Graph node(s)</th><th>What it does</th></tr></thead>
            <tbody>{AGENTS.map((a) => (
              <tr key={a.name}>
                <td><strong>{a.name}</strong></td>
                <td className="small">{a.ai}</td>
                <td><code className="small">{a.nodes}</code></td>
                <td className="small"><ul style={{ margin: 0, paddingLeft: "1.1rem" }}>{a.does.map((d) => <li key={d}>{d}</li>)}</ul></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Human approval gates</h2>
          <ul className="small">
            <li><strong>Approve requirements.</strong> If there are blocking questions, they go to the right stakeholder roles first;
              answers become new inputs and the agents run again (at most two rounds). Then the baseline is signed off: the product
              owner always, compliance if there are regulatory items or legal-review flags, infosec if there are high-severity
              security issues, and the architect if there are must-have integration or performance requirements. Requirements
              owned by a role must be accepted, modified or rejected by that role.</li>
            <li><strong>Approve plan.</strong> The SDLC model is approved by the project manager, architect, infosec and compliance;
              choosing a different model rebuilds the workflow for it. Then the workflow is approved.</li>
            <li>Every step supports approve, regenerate with feedback, and per-item edits. All decisions are audited.</li>
          </ul>
        </section>
        <section className="card">
          <h2>Interview graph</h2>
          <p className="small muted">The adaptive stakeholder interview, kept separate from the analysis flow. Its transcript is saved as an input source.</p>
          {graphs && <Diagram code={graphs.interview} />}
        </section>
      </div>
    </main>
  );
}
