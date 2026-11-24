import { useState } from "react";
import type { ClarificationGate, Decision } from "../../api";
import { useCatalog } from "../../catalog";

interface Props { gate: ClarificationGate; busy: boolean; onDecide: (label: string, d: Decision) => void }

export default function ClarificationGateView({ gate, busy, onDecide }: Props) {
  const catalog = useCatalog();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [responder, setResponder] = useState("business_analyst");
  const [feedback, setFeedback] = useState("");
  const answered = Object.values(answers).filter((a) => a.trim()).length;

  function submit(skip: boolean) {
    onDecide(skip ? "Skipping clarification…" : "Storing answers as new sources and re-running the agents…", {
      gate: "clarification", responder, skip,
      answers: gate.questions.map((q) => ({ question: q.question, target_role: q.target_role, answer: answers[q.question] ?? "" })),
    });
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Clarification needed: round {gate.round} of {gate.max_rounds}</h2>
        <p className="muted small">
          The clarification agent found gaps that block the baseline, and routed each question to the stakeholder best placed to
          answer it. Answers are masked, stored as sources for that role, and the agents re-run.
        </p>
      </section>
      {Object.entries(gate.by_role).map(([role, questions]) => (
        <section key={role} className="card">
          <h3>Ask: {catalog.role[role]?.name ?? role}</h3>
          {questions.map((q) => (
            <label key={q.question} className="question">
              <span>
                {q.severity === "blocking" && <span className="tag prio-must">blocking</span>} {q.question}
                {q.related_req_ids.length > 0 && <span className="muted small"> · {q.related_req_ids.join(", ")}</span>}
              </span>
              <span className="muted small">{q.reason}</span>
              <textarea rows={2} value={answers[q.question] ?? ""}
                onChange={(e) => setAnswers({ ...answers, [q.question]: e.target.value })} />
            </label>
          ))}
        </section>
      ))}
      <section className="card">
        <label>Questions not useful? Explain why and regenerate the analysis
          <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)}
            placeholder="e.g. Thresholds are defined in the credit policy; do not ask about them" />
        </label>
        <div><button disabled={busy || !feedback.trim()} onClick={() => onDecide("Regenerating the analysis with your feedback…",
          { gate: "clarification", responder, decision: "regenerate", feedback, answers: [] })}>Regenerate analysis</button></div>
        <p className="muted small">Leaving a question unanswered rejects it; answering accepts it and adds the answer as a source.</p>
      </section>
      <div className="sticky-actions">
        <label className="row">Responder <input value={responder} onChange={(e) => setResponder(e.target.value)} /></label>
        <div className="row">
          <button disabled={busy} onClick={() => submit(true)}>Skip to approval</button>
          <button className="primary" disabled={busy || answered === 0} onClick={() => submit(false)}>
            Submit {answered} answer(s)
          </button>
        </div>
      </div>
    </div>
  );
}
