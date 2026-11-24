import { useState, type FormEvent } from "react";
import { api, type InterviewSession, type InterviewTopicStatus, type Project } from "../api";
import { useCatalog } from "../catalog";

interface Props { project: Project; role: string; onCompleted: () => void }

const FOLLOW_UP: Record<string, string> = {
  vague: "Follow-up: answer was vague", incomplete: "Follow-up: points missing",
  inconsistent: "Follow-up: conflicts with earlier answer", off_topic: "Follow-up: off topic",
};
const QUALITY: Record<string, [string, string]> = {
  complete: ["complete", "ok"], incomplete: ["incomplete", "sev-medium"], vague: ["vague", "sev-medium"],
  inconsistent: ["inconsistent", "sev-high"], unknown: ["didn't know", "sev-low"], off_topic: ["off topic", "sev-medium"],
  skipped: ["skipped", "sev-low"],
};
const STATUS: Record<string, [string, string]> = {
  covered: ["✓", "covered"], partial: ["◐", "partly covered"], in_progress: ["→", "in progress"],
  skipped: ["–", "skipped"], pending: ["○", "not started"],
};

/** Adaptive interview (step 7): topic checklist, answer assessment and targeted follow-ups. */
export default function AiInterview({ project, role, onCompleted }: Props) {
  const catalog = useCatalog();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<InterviewSession>) {
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setSession(s);
      setAnswer("");
      if (s.status === "completed") onCompleted();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const reply = (text: string, finish = false) => session && run(() => api.replyInterview(project.id, session.session_id, text, finish));
  function send(e: FormEvent) { e.preventDefault(); reply(answer); }

  if (!session) {
    return (
      <section className="card stack">
        <p>
          The AI interviewer covers the topics that matter for {catalog.role[role].name.toLowerCase()}, in an order that follows
          the conversation. It checks every answer and follows up when one is incomplete, vague ("fast", "secure") or
          inconsistent with something said earlier. Points answered in passing are not asked again.
        </p>
        <p className="note">Answers are masked before the interviewer sees them. Avoid entering personal data.</p>
        {error && <div className="alert error">{error}</div>}
        <div><button className="primary" disabled={busy} onClick={() => run(() => api.startInterview(project.id, role))}>
          {busy ? "Preparing first question…" : "Start AI interview"}
        </button></div>
      </section>
    );
  }

  const q = session.question;
  return (
    <section className="interview">
      <div className="card stack">
        <div className="chat">
          {session.transcript.map((t) => (
            <div key={t.turn}>
              <div className="bubble agent">
                <QuestionHead topic={t.topic_name} kind={t.follow_up_kind} />
                {t.question}
              </div>
              <div className="bubble user">{t.answer || <em className="muted">(skipped)</em>}</div>
              {t.assessment && <Assessment a={t.assessment} />}
            </div>
          ))}
          {q && (
            <div className="bubble agent current">
              <QuestionHead topic={q.topic_name} kind={q.follow_up_kind} />
              {q.question}
              {q.missing.length > 0 && <div className="small muted">Still needed: {q.missing.join("; ")}</div>}
            </div>
          )}
        </div>
        {error && <div className="alert error">{error}</div>}
        {session.status === "awaiting_answer" ? (
          <form onSubmit={send} className="stack">
            <textarea rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Type the stakeholder's answer…" autoFocus />
            <div className="row">
              <button type="submit" className="primary" disabled={busy || !answer.trim()}>{busy ? "Assessing answer…" : "Send"}</button>
              <button type="button" disabled={busy} onClick={() => reply("")} title="Move on; the topic's points become open questions">Skip topic</button>
              <button type="button" disabled={busy} onClick={() => reply(answer, true)}>Finish interview</button>
            </div>
          </form>
        ) : (
          <Summary session={session} roleName={(id) => catalog.role[id]?.name ?? id} />
        )}
      </div>
      <TopicChecklist topics={session.topics} current={q?.topic} />
    </section>
  );
}

function QuestionHead({ topic, kind }: { topic: string; kind: string | null }) {
  return (
    <div className="q-head">
      <span className="eyebrow">{topic}</span>
      {kind && <span className="tag accent">{FOLLOW_UP[kind] ?? "Follow-up"}</span>}
    </div>
  );
}

function Assessment({ a }: { a: NonNullable<InterviewSession["transcript"][number]["assessment"]> }) {
  const [label, cls] = QUALITY[a.quality] ?? [a.quality, ""];
  return (
    <div className="assessment small">
      <span className={`tag ${cls}`}>{label}</span>
      {a.vague_phrases.length > 0 && <span className="muted"> unmeasurable: {a.vague_phrases.map((p) => `“${p}”`).join(", ")}</span>}
      {a.note && <span className="muted"> · {a.note}</span>}
    </div>
  );
}

function TopicChecklist({ topics, current }: { topics: InterviewTopicStatus[]; current?: string }) {
  const done = topics.filter((t) => t.status === "covered").length;
  return (
    <aside className="card topics" aria-label="Interview topics">
      <div className="section-head"><h3>Topics</h3><span className="small muted num">{done}/{topics.length} covered</span></div>
      <ol>
        {topics.map((t) => {
          const [mark, label] = STATUS[t.status] ?? ["○", t.status];
          return (
            <li key={t.id} className={`topic status-${t.status} ${t.id === current ? "current" : ""}`}>
              <div className="topic-head">
                <span className="mark" aria-hidden>{mark}</span>
                <span className="grow">{t.name}</span>
                {t.priority === "secondary" && <span className="small muted">secondary</span>}
              </div>
              <div className="small muted">{label}{t.follow_ups > 0 && ` · ${t.follow_ups} follow-up${t.follow_ups > 1 ? "s" : ""}`}</div>
              {(t.status !== "pending" || t.slots.some((s) => s.answered)) && (
                <ul className="slots">
                  {t.slots.map((s) => (
                    <li key={s.id} className={s.answered ? "answered" : ""}>
                      <span aria-hidden>{s.answered ? "✓" : "·"}</span> {s.label}
                      {s.in_passing && <span className="muted"> (in passing)</span>}
                      <span className="visually-hidden">{s.answered ? " answered" : " open"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function Summary({ session, roleName }: { session: InterviewSession; roleName: (id: string) => string }) {
  const open = session.open_questions;
  const unresolved = session.contradictions.filter((c) => !c.resolved);
  return (
    <div className="stack">
      <div className="alert ok">
        Interview complete. {session.source_id
          ? `The transcript, topic coverage and open points were saved as an input source (${Math.round((session.summary?.slot_coverage ?? 0) * 100)}% of checklist points answered; primary topics covered ${session.summary?.primary_covered}).`
          : "No answers were given, so nothing was saved."}
      </div>
      {open.length > 0 && (
        <div>
          <h3>Open points</h3>
          <ul className="issues">
            {open.map((o, i) => (
              <li key={i} className="stripe medium small">{o.question}
                <span className="muted"> · {o.reason}{o.target_role && ` · ask ${roleName(o.target_role)}`}</span></li>
            ))}
          </ul>
        </div>
      )}
      {unresolved.length > 0 && (
        <div>
          <h3>Unresolved inconsistencies</h3>
          <ul className="issues">
            {unresolved.map((c, i) => <li key={i} className="stripe high small">Turn {c.turn} vs turn {c.earlier_turn}: {c.explanation}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
