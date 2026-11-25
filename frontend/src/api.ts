// Typed client for the FastAPI backend (proxied at /api by Vite).

export interface Category { id: string; name: string; description: string }
export interface Role {
  id: string; name: string; description: string; provides: string;
  categories: { primary: string[]; secondary: string[] };
}
export interface Domain {
  id: string; status: "active" | "planned"; code: string; name: string; description: string;
  typical_regulations: string[]; required_roles: string[]; mandatory_categories: string[];
  key_questions: { role: string; category: string; question: string }[];
}
export interface SourceType {
  id: string; name: string; structured: boolean; default_sensitivity: Sensitivity;
  formats: string[]; typical_roles: string[]; extraction_guidance: string;
}
export interface Output { id: string; name: string; description: string; produced_by: string; status: string }
export interface Catalog {
  categories: Category[]; roles: Role[]; domains: Domain[]; sources: SourceType[]; outputs: Output[];
}

export type Sensitivity = "public" | "internal" | "confidential" | "restricted";

export interface Project { id: number; name: string; domain: string; status: string; jurisdiction: string; deployment_stage?: "advisory" | "assisted" }

export interface Source {
  id: number; source_type: string; stakeholder_role: string | null; title: string; filename: string | null;
  content_sha256: string; char_count: number; sensitivity: Sensitivity; redactions: Record<string, number>;
  masking_engine: string; injection_flags: string[]; created_at: string; masked_text: string | null;
}

export interface InterviewSection {
  category: string; topic: string; questions: string[]; example_requirement: string;
  priority: "primary" | "secondary" | "domain";
}
export interface InterviewTemplate { role: Role; domain: string | null; sections: InterviewSection[] }

export type ReqStatus = "proposed" | "suggested" | "accepted" | "rejected" | "modified";
export interface Requirement {
  id: string; statement: string; type: "functional" | "non_functional"; categories: string[];
  priority: "must" | "should" | "could"; acceptance_criteria: string[]; source_quote: string;
  confidence: number; source_id: number | null; source_title: string; source_type: string | null;
  stakeholder_role: string | null; origin: string; status: ReqStatus; rationale?: string;
  classification_rationale?: string; original_statement?: string;
  grounding_support?: GroundingSupport; grounding_note?: string; citations?: Citation[];
  extraction_confidence?: number; escalated?: boolean; escalation_reasons?: string[];
  business_justification?: string; assumptions?: string[]; dependencies?: string[]; depends_on?: string[];
  applicable_regulations?: string[]; risk_level?: "low" | "medium" | "high";
}
export interface Trace { req_id: string; stakeholder_role: string | null; source_id: number | null; source_title: string | null; source_quote: string; citations: string[] }
export interface Returned { req_id: string; statement: string; stakeholder_role: string | null; blocking: boolean;
  checks: { check: string; message: string; severity: string }[] }
export type GroundingSupport = "supported" | "partially_supported" | "unsupported" | "contradicts_evidence" | "no_obligation_expected";
export interface Citation { ref: string; citation: string; strength: "strong" | "weak" | "none"; issuer?: string; version?: string }
export interface Issue { req_id: string | null; type: string; message: string; severity: "high" | "medium" | "low"; check?: string | null }
export interface Clarification {
  question: string; target_role: string; related_req_ids: string[]; severity: "blocking" | "non_blocking"; reason: string;
}
export interface Conflict { kind: string; req_ids: string[]; description: string; suggested_resolution: string }
export interface ComplianceMapping {
  req_id: string; regulation: string; obligation: string; evidence: string; evidence_ref: string;
  confidence: number; needs_legal_review: boolean; jurisdiction?: string; obligation_type?: string;
  required_controls?: string[]; retention_period?: string; impact?: "high" | "medium" | "low"; citation?: string;
  legal_approval?: { by: string; at: string }; id?: string; evidence_strength?: string;
  legal_decision?: { action: string; by: string; at: string; note: string }; original?: { regulation: string; obligation: string };
}
export interface ComplianceCheckpoint { name: string; stage: string; approver_role: string; regulation: string; req_ids: string[] }
export interface Obligation { kind: string; regulation: string; jurisdiction: string; obligation: string; period: string; req_id: string; citation?: string | null }
export interface ComplianceGap { regulation: string; description: string; suggested_requirement: string; addressed_by?: string | null }
export interface Compliance {
  mappings: ComplianceMapping[]; gaps: ComplianceGap[]; evidence: { ref: string; source: string }[];
  checkpoints?: ComplianceCheckpoint[]; retention_and_reporting?: Obligation[]; determination?: string;
}
export interface SecurityFinding {
  req_id: string | null; kind: string; description: string; suggested_requirement: string; severity: "high" | "medium" | "low";
}
export interface Risk {
  id: string; title: string; type: string; description: string; likelihood: number; impact: number;
  score: number; level: "high" | "medium" | "low"; mitigation: string; related_req_ids: string[];
}
export interface Approval { role: string; reviewer: string; decision: string; feedback: string; at: string; selected_model?: string | null }
export interface SdlcRecommendation {
  model: string; model_id: string; score: number; raw?: number; topsis: number; fit: number;
  characteristics_fit?: number | null; characteristics?: Record<string, { matched: number; answered: number; mismatched: string[] }>;
  rule_adjustments: RuleAdjustment[]; key_drivers: string[]; concerns: string[]; source?: string;
}
export type Answer = "yes" | "no" | "unknown";
export interface SdlcCharacteristic {
  id: string; text: string; category: string; category_name: string;
  answer: "yes" | "no" | null; source: "human" | "derived" | "llm" | "unknown"; reason: string;
}
export interface Quality { completeness: number; consistency: number; evidence: number; testability: number; grounding?: number; overall: number;
  checks?: Record<string, number>; requirements_passing?: number }

export interface ClarificationGate {
  gate: "clarification"; round: number; max_rounds: number; questions: Clarification[];
  by_role: Record<string, Clarification[]>;
}
export interface BaselineGate {
  gate: "baseline"; required_approvers: string[]; pending_approvers: string[]; approvals: Approval[];
  requirements: Requirement[]; escalated: string[]; issues: Issue[]; quality: Quality; conflicts: Conflict[];
  decision_items?: Record<string, DecisionItem>; interpretations?: ComplianceMapping[];
  clarifications: Clarification[]; compliance: Compliance; security_findings: SecurityFinding[]; risks: Risk[];
  returned?: Returned[];
}
export interface SdlcGate {
  gate: "sdlc"; required_approvers: string[]; pending_approvers: string[]; approvals: Approval[];
  recommendations: SdlcRecommendation[]; factors: Record<string, unknown>; selected_model: string | null;
  rules_fired: { rule: string; reason: string; source?: string }[]; explanation: SdlcExplanation;
  characteristics?: SdlcCharacteristic[]; rules_version?: string;
}
export type Gate = ClarificationGate | BaselineGate | SdlcGate | WorkflowGate;

export interface SdlcCatalog {
  version: string; scoring: Record<string, number>;
  factors: { id: string; name: string; base_weight: number }[];
  characteristics: { id: string; name: string; questions: string[] }[];
  models: { id: string; name: string; description: string; source?: string; structure: string; cadence: string;
    phases: { name: string; kinds: string[]; recurrence: string }[] }[];
  rules: { id: string; source: string; reason: string; effects: Record<string, number> }[];
  mandatory_controls: { control: string; phase: string; when: string }[];
}

export interface RunStatus {
  project_id: number;
  status: "awaiting_input" | "completed" | "running" | "not_started" | "outdated";
  gate: Gate["gate"] | null;
  next: string[];
  pending: Gate | null;
  state: { iteration?: number; clarification_round?: number; quality?: Quality; requirements?: Requirement[] };
}

export interface StandardRecord {
  id: string; statement: string; categories: string[]; source_stakeholder: string | null; business_justification: string;
  priority: string; dependencies: string[]; assumptions: string[]; acceptance_criteria: string[];
  applicable_regulations: string[]; risk_level: string; confidence: number; approval_status: string; trace: Trace;
}
export interface ProcessWorkflow { id: string; use_case: string; title: string; actor: string; mermaid: string; requirement_ids: string[]; trace: Trace[] }
export interface DataRequirement { req_id: string; statement: string; categories: string[]; retention: string[]; regulations: string[]; source_sensitivity: string | null; trace: Trace }
export interface ThreatRiskRow {
  entry: "risk" | "threat"; id: string; title: string; type: string; description: string; level: string; mitigation: string;
  related_req_ids: string[]; score?: number; likelihood?: number; impact?: number; control_requirement?: string | null;
  citation?: string | null; trace: Trace[];
}
export interface UserStory { req_id: string; as_a: string; i_want: string; so_that: string; acceptance_criteria: string[] }
export interface RtmRow {
  req_id: string; statement: string; type: string; priority: string; status: string; origin: string;
  stakeholder_role: string | null; source_title: string | null; source_sha256: string | null;
  regulations: string[]; risks: string[]; user_story: boolean; use_cases: string[]; sdlc_phase: string | null;
  citations: string[]; grounding_support: GroundingSupport | null; confidence: number; escalated: boolean;
  tests: number; approved_by: string[]; source_quote?: string; business_justification?: string; risk_level?: string;
}
export interface Artifacts {
  srs_markdown: string; user_stories: UserStory[]; use_cases: UseCase[]; sdlc_workflow: SdlcWorkflow; traceability_matrix: RtmRow[];
  compliance_matrix: Compliance; risk_register: Risk[]; open_issues: ((Clarification | Issue) & { trace?: Trace[] })[];
  requirements: StandardRecord[]; process_workflows: ProcessWorkflow[]; data_requirements: DataRequirement[];
  interface_requirements: { req_id: string; statement: string; dependencies: string[]; acceptance_criteria: string[]; trace: Trace }[];
  threat_risk_register: ThreatRiskRow[]; assumptions_dependencies: { id: string; kind: "assumption" | "dependency"; text: string; req_id: string; on_requirement?: boolean; trace: Trace }[];
  sdlc: { decision: { model: string }; recommendations: SdlcRecommendation[]; factors: Record<string, unknown>;
    rules_fired: { rule: string; reason: string }[]; explanation: SdlcExplanation; approvals: Approval[] };
}

export interface InterviewTopicStatus {
  id: string; name: string; priority: "primary" | "secondary"; follow_ups: number;
  status: "pending" | "in_progress" | "covered" | "partial" | "skipped";
  slots: { id: string; label: string; quantified?: boolean; answered: boolean; in_passing: boolean }[];
}
export interface InterviewSession {
  session_id: string; role: string; status: "awaiting_answer" | "completed";
  question: { question: string; topic: string; topic_name: string; category: string; is_follow_up: boolean;
    follow_up_kind: string | null; reason: string; missing: string[]; turn: number } | null;
  transcript: { turn: number; topic: string; topic_name: string; question: string; category: string; is_follow_up: boolean;
    follow_up_kind: string | null; answer: string;
    assessment?: { quality: string; vague_phrases: string[]; missing: string[]; note: string; follow_up: string | null } }[];
  topics: InterviewTopicStatus[];
  summary: { topics: number; by_status: Record<string, number>; slot_coverage: number; primary_covered: string } | null;
  open_questions: { topic: string; slot: string; question: string; target_role: string | null; reason: string }[];
  contradictions: { turn: number; earlier_turn: number | null; topic: string; explanation: string; resolved: boolean }[];
  source_id: number | null;
}

export type Decision =
  | { gate: "clarification"; responder: string; skip?: boolean; decision?: "answer" | "regenerate"; feedback?: string;
      answers: { question: string; target_role: string; answer: string }[] }
  | { gate: "baseline"; decision: "approve" | "regenerate"; reviewer: string; reviewer_role: string; feedback: string;
      edits: { id: string; action: "accept" | "reject" | "modify"; statement?: string }[];
      interpretations?: { id: string; action: "accept" | "reject" | "modify"; regulation?: string; obligation?: string; note?: string }[] }
  | { gate: "workflow"; decision: "approve" | "regenerate"; reviewer: string; reviewer_role: string; feedback: string;
      edits?: WorkflowEdit[]; schedule?: Record<string, number> }
  | { gate: "sdlc"; decision: "approve" | "regenerate"; reviewer: string; reviewer_role: string; feedback: string;
      selected_model?: string | null; characteristic_answers?: Record<string, Answer> };
export interface KbDoc {
  id: number; doc_key: string; version: string; collection: string; title: string;
  source: { issuer: string; url: string | null; license: string; sha256: string };
  jurisdictions: string[]; effective_from: string; effective_to: string | null; review_due: string | null;
  review_overdue: boolean; applicability: { domains: string[]; entity_types?: string[]; products?: string[]; roles?: string[] };
  status: "draft" | "active" | "superseded" | "withdrawn" | "rejected"; in_force: boolean;
  submitted_by: string; approved_by: string | null; approved_role: string | null; approved_at: string | null;
  section_count: number; chunk_count: number; embedding_model: string | null; redactions: Record<string, number>;
  notes: string | null; created_at: string;
}
export interface KbDiff { added: string[]; removed: string[]; changed: string[]; unchanged: number }
export interface KbDetail {
  document: KbDoc; content: string; versions: KbDoc[]; diff_vs: string | null; diff: KbDiff;
  sections: { path: string[]; clause_ref: string | null; passages: number }[];
}
export interface KbCollection { id: string; name: string; description: string; approver_roles: string[]; searchable: boolean; chunking: string }
export interface KbMeta { collections: KbCollection[]; licenses: string[]; jurisdictions: Record<string, string>; agent_allowlist: Record<string, string[]> }
export interface KbHit {
  ref: string; doc_key: string; title: string; version: string; collection: string; issuer: string; source_url: string | null;
  jurisdictions: string[]; effective_from: string; effective_to: string | null; applicability: { domains: string[] };
  section_path: string[]; clause_ref: string | null; passage: string; context: string; citation: string;
  strength: "strong" | "weak" | "none";
  scores: { vector_rank: number | null; lexical_rank: number | null; rrf: number; similarity: number; rerank: number | null; method: string };
}
export interface GroundedAnswerResult {
  question: string; answer: string; confidence: number; escalated: boolean; escalation_reasons: string[]; review_id: number | null;
  classification: { intent: string; collections: string[]; search_queries: string[]; reason: string };
  claims: { text: string; refs: string[]; invalid_refs: string[]; citations: string[] }[];
  citations: (Citation & { effective_from: string })[];
  components: { llm: number; citation_coverage: number; evidence_strength: string };
}
export interface ReviewQueueItem {
  id: number; project_id: number | null; kind: string; subject: string; payload: GroundedAnswerResult;
  reasons: string[]; requested_by: string; status: string; created_at: string;
}
export interface KbImpact {
  id: number; project_id: number; doc_key: string; old_version: string; new_version: string | null;
  change: string; cited_refs: string[]; created_at: string;
}

export interface RuleAdjustment { rule: string; points: number; reason: string; source?: string }
export interface WorkflowPhase {
  name: string; objective: string; activities: string[]; responsible_roles: string[]; deliverables: string[];
  security_activities: string[]; testing: string[]; compliance_checkpoints: string[]; entry_criteria: string[];
  exit_criteria: string[]; approval_gate: { name: string; approvers: string[]; criteria: string[]; hitl_control?: string };
  requirement_ids: string[]; traceability?: string[]; duration_weeks?: number; kinds?: string[]; recurrence?: string;
  timing?: string; occurrences?: { start: number; end: number; label: string }[]; pairs_with?: string; designed_in?: string;
}
export interface SdlcWorkflow {
  model: string; phases: WorkflowPhase[]; cadence: string; traceability: string; structure?: string; model_cadence?: string;
  controls_added_by_rules: { phase: string; field: string; control: string; reason: string }[];
  requirements_not_assigned: string[]; phases_added_by_rules?: string[]; phases_dropped?: string[];
  component_plan?: { component: string; how: string; model_norm: string; source: "project" | "model default" }[];
  schedule?: { iterations?: number; iteration_length_weeks?: number; iterations_per_release?: number; cycles?: number;
    start_date: string; total_weeks: number };
  gantt?: string; human_edits?: WorkflowEdit[];
}
export interface WorkflowEdit { phase: string; field: string; value: number | string | string[] }
export interface WorkflowGate {
  gate: "workflow"; required_approvers: string[]; pending_approvers: string[]; approvals: Approval[]; workflow: SdlcWorkflow;
}
export interface DecisionItem { owner: string; reasons: string[]; controls: string[]; decided: boolean }
export interface HitlControl {
  id: string; name: string; where: string; who: string; actions: string; status: string; evidence: string[];
  open?: string[]; required_roles?: string[];
}
export interface ApprovalRequest {
  id: number; kind: "change_request" | "production_readiness"; title: string; required_roles: string[]; pending_roles: string[];
  decisions: { role: string | null; reviewer: string; decision: string; comment?: string; at: string }[];
  status: string; created_by: string; created_role: string; created_at: string | null; closed_at: string | null;
  payload: {
    action?: "add" | "modify" | "remove"; req_id?: string | null; statement?: string | null; reason?: string;
    current_statement?: string | null; revisions?: number; release?: string;
    impact?: { level: string; categories: string[]; dependent_requirements: string[]; use_cases: string[]; user_stories: string[];
      acceptance_tests: number; regulations: string[]; risks: string[]; workflow_phases: string[]; artefacts_to_regenerate: string[] };
    checklist?: ReadinessItem[];
  };
}
export interface ReadinessItem {
  id: string; label: string; kind: "automatic" | "attestation"; owner: string; status: "pass" | "fail" | "pending" | "waived";
  evidence?: string; attested_by?: string; waiver?: { by: string; justification: string };
}
export interface UseCase {
  id: string; title: string; primary_actor: string; preconditions: string[]; main_flow: string[];
  alternative_flows: string[]; exception_flows: string[]; postconditions: string[]; requirement_ids: string[];
}
export interface SdlcExplanation { summary: string; reasons: string[]; alternatives: { model: string; why_not: string }[]; revisit_if: string[] }

export interface AuditEntry { at: string; actor: string; action: string; detail: Record<string, unknown> }
export interface Health { status: string; db: string; model: string; llm_configured: boolean }

export interface Me { username: string; display_name: string; roles: string[]; mfa_verified: boolean; mfa_required: boolean }
export interface AdminUser { id: number; username: string; display_name: string; roles: string[]; active: boolean; mfa_enabled: boolean; locked: boolean }
export interface Member { user_id: number; username: string; display_name: string; roles: string[]; added_by: string }
export interface UsageRow { agent: string; model: string; calls: number; input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number }
export interface Usage { calls: number; input_tokens: number; output_tokens: number; cost_usd: number; by_agent_model: UsageRow[] }
export interface EvaluationStatus { fingerprint: string; current_evaluation_passed: boolean; re_evaluation_required: boolean;
  passing_run: { id: number; case: string; at: string } | null; last_run: { id: number; case: string; passed: boolean | null; at: string } | null;
  changes_since_last_run: string[] }
export interface Deployment { stage: "advisory" | "assisted"; require_current_evaluation: boolean; reason?: string; evaluation: EvaluationStatus }
export interface QualityMonitor { requirement_correction_rate: number | null; interpretation_correction_rate: number | null; sdlc_override_rate: number | null;
  compliance_gaps_found_by_agent: number; compliance_gaps_found_after_approval: number;
  kb_answers: Record<string, number>; totals: Record<string, number>; trend: Record<string, Record<string, number>> }
export interface DomainReadiness { domain: string; name: string; status: string; ready: boolean; checks: Record<string, boolean>; knowledge: Record<string, number> }
export interface ArtifactVersion { version: number; status: string; created_at: string; superseded_at: string | null; kinds: string[] }
export interface AnalystComparison { analyst: string; threshold: number; analyst_requirements: number; ai_requirements: number;
  agreement: { precision: number; recall: number; f1: number }; matched: { analyst: string; ai: string; similarity: number }[];
  only_analyst: string[]; only_ai: { id: string; statement: string }[] }
export interface FeedbackRow { role: string; sus_score: number; usefulness: number; trust: number; comment: string; at: string }
export interface RetentionPolicy { id: string; data: string; keep_days: number; basis: string; due: number; projects_on_legal_hold: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Same-origin (Vite proxy): the HttpOnly session cookie is sent automatically and is never readable by scripts.
  const res = await fetch(`/api${path}`, { credentials: "same-origin", ...init });
  if (res.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("auth-required"));
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error */ }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/health"),
  me: () => request<Me>("/auth/me"),
  login: (username: string, password: string) =>
    request<{ token: string; mfa: "none" | "verify" | "enroll" }>("/auth/login", json("POST", { username, password })),
  mfaVerify: (code: string) => request<{ mfa: string }>("/auth/mfa/verify", json("POST", { code })),
  mfaEnroll: () => request<{ secret: string; otpauth_uri: string }>("/auth/mfa/enroll", json("POST")),
  mfaConfirm: (code: string) => request<{ mfa: string }>("/auth/mfa/confirm", json("POST", { code })),
  logout: () => request<void>("/auth/logout", json("POST")),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/password", json("POST", { current_password, new_password })),
  adminUsers: () => request<AdminUser[]>("/admin/users"),
  createUser: (body: { username: string; display_name: string; password: string; roles: string[] }) =>
    request<AdminUser>("/admin/users", json("POST", body)),
  setRoles: (id: number, roles: string[]) => request<AdminUser>(`/admin/users/${id}/roles`, json("POST", { roles })),
  resetMfa: (id: number) => request<void>(`/admin/users/${id}/reset-mfa`, json("POST")),
  setActive: (id: number, active: boolean) => request<void>(`/admin/users/${id}/active`, json("POST", { active })),
  members: (pid: number) => request<Member[]>(`/projects/${pid}/members`),
  addMember: (pid: number, username: string) => request<Member[]>(`/projects/${pid}/members`, json("POST", { username })),
  removeMember: (pid: number, userId: number) => request<void>(`/projects/${pid}/members/${userId}`, json("DELETE")),
  legalHold: (pid: number, hold: boolean, reason: string) => request<void>(`/projects/${pid}/legal-hold`, json("POST", { hold, reason })),
  archive: (pid: number) => request<void>(`/projects/${pid}/archive`, json("POST")),
  auditVerify: () => request<{ valid: boolean; checked: number; broken_at: number | null }>("/admin/audit/verify"),
  retention: () => request<RetentionPolicy[]>("/admin/retention"),
  applyRetention: () => request<Record<string, number>>("/admin/retention/apply", json("POST")),
  provenance: () => request<Record<string, unknown>>("/admin/provenance"),
  catalog: () => request<Catalog>("/catalog"),

  // Step 20: deploy, monitor, improve
  deployment: () => request<Deployment>("/admin/deployment"),
  setDeployment: (body: { stage: string; require_current_evaluation: boolean; reason: string }) =>
    request<Deployment>("/admin/deployment", json("POST", body)),
  quality: () => request<QualityMonitor>("/admin/quality"),
  systemUsage: () => request<Usage>("/admin/usage"),
  domains: () => request<DomainReadiness[]>("/admin/domains"),
  setDomain: (id: string, active: boolean, justification: string) =>
    request<DomainReadiness>(`/admin/domains/${id}`, json("POST", { active, justification })),
  projectUsage: (pid: number) => request<Usage>(`/projects/${pid}/usage`),
  artifactHistory: (pid: number) => request<ArtifactVersion[]>(`/projects/${pid}/artifacts/history`),
  analystComparison: (pid: number, requirements: string[], threshold = 0.8) =>
    request<AnalystComparison>(`/projects/${pid}/analyst-comparison`, json("POST", { requirements, threshold })),
  feedback: (pid: number) => request<FeedbackRow[]>(`/projects/${pid}/feedback`),
  submitFeedback: (pid: number, body: { role: string; sus: number[]; usefulness: number; trust: number; comment: string }) =>
    request<{ sus_score: number }>(`/projects/${pid}/feedback`, json("POST", body)),
  accountabilityPack: (pid: number) => request<Record<string, unknown>>(`/projects/${pid}/accountability-pack`),
  interviewTemplate: (role: string, domain: string) =>
    request<InterviewTemplate>(`/catalog/roles/${role}/interview?domain=${domain}`),

  projects: () => request<Project[]>("/projects"),
  project: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (name: string, domain: string, jurisdiction = "IN") =>
    request<Project>("/projects", json("POST", { name, domain, jurisdiction })),

  sources: (pid: number) => request<Source[]>(`/projects/${pid}/sources`),
  source: (pid: number, sid: number) => request<Source>(`/projects/${pid}/sources/${sid}`),
  addSource: (pid: number, form: FormData) => request<Source>(`/projects/${pid}/sources`, { method: "POST", body: form }),
  deleteSource: (pid: number, sid: number) => request<void>(`/projects/${pid}/sources/${sid}`, { method: "DELETE" }),
  submitInterview: (pid: number, body: { stakeholder_role: string; title?: string; answers: { category: string; question: string; answer: string }[] }) =>
    request<Source>(`/projects/${pid}/interviews`, json("POST", body)),

  startInterview: (pid: number, role: string) =>
    request<InterviewSession>(`/projects/${pid}/interview-sessions`, json("POST", { stakeholder_role: role })),
  replyInterview: (pid: number, sid: string, answer: string, finish = false) =>
    request<InterviewSession>(`/projects/${pid}/interview-sessions/${sid}/reply`, json("POST", { answer, finish })),

  sdlcCatalog: () => request<SdlcCatalog>("/catalog/sdlc"),
  run: (pid: number) => request<RunStatus>(`/projects/${pid}/run`),
  startRun: (pid: number) => request<RunStatus>(`/projects/${pid}/runs`, { method: "POST" }),
  decide: (pid: number, decision: Decision) => request<RunStatus>(`/projects/${pid}/decision`, json("POST", decision)),
  hitl: (pid: number) => request<HitlControl[]>(`/projects/${pid}/hitl`),
  requirements: (pid: number) => request<{ req_id: string; statement: string; approval_status: string; version?: number }[]>(`/projects/${pid}/requirements`),
  changeRequests: (pid: number) => request<ApprovalRequest[]>(`/projects/${pid}/change-requests`),
  proposeChange: (pid: number, body: { requested_by: string; role: string; action: string; req_id?: string; statement?: string;
    reason: string; categories?: string[]; priority?: string; type?: string }) =>
    request<ApprovalRequest>(`/projects/${pid}/change-requests`, json("POST", body)),
  decideChange: (pid: number, id: number, body: { reviewer: string; reviewer_role: string; decision: string; comment: string }) =>
    request<ApprovalRequest>(`/projects/${pid}/change-requests/${id}/decision`, json("POST", body)),
  reviseChange: (pid: number, id: number, body: { requested_by: string; statement: string; reason: string }) =>
    request<ApprovalRequest>(`/projects/${pid}/change-requests/${id}/revise`, json("POST", body)),
  regenerateArtifacts: (pid: number, body: { requested_by: string; role: string }) =>
    request<{ status: string }>(`/projects/${pid}/artifacts/regenerate`, json("POST", body)),
  readinessReviews: (pid: number) => request<ApprovalRequest[]>(`/projects/${pid}/readiness-reviews`),
  openReadiness: (pid: number, body: { requested_by: string; role: string; release: string }) =>
    request<ApprovalRequest>(`/projects/${pid}/readiness-reviews`, json("POST", body)),
  decideReadiness: (pid: number, id: number, body: { reviewer: string; reviewer_role: string; decision: string; comment: string;
    attest: string[]; waivers: Record<string, string> }) =>
    request<ApprovalRequest>(`/projects/${pid}/readiness-reviews/${id}/decision`, json("POST", body)),
  artifacts: (pid: number) => request<Artifacts>(`/projects/${pid}/artifacts`),
  audit: (pid: number) => request<AuditEntry[]>(`/projects/${pid}/audit`),
  graph: () => request<{ analysis: string; interview: string }>("/graph"),

  kbMeta: () => request<KbMeta>("/kb/meta"),
  kbDocuments: (collection?: string, status?: string) => {
    const q = new URLSearchParams();
    if (collection) q.set("collection", collection);
    if (status) q.set("status", status);
    return request<KbDoc[]>(`/kb/documents?${q}`);
  },
  kbDocument: (id: number) => request<KbDetail>(`/kb/documents/${id}`),
  kbSubmit: (form: FormData) => request<{ document: KbDoc; diff: KbDiff }>("/kb/documents", { method: "POST", body: form }),
  kbApprove: (id: number, actor: string, role: string) => request<KbDoc>(`/kb/documents/${id}/approve`, json("POST", { actor, role })),
  kbReject: (id: number, actor: string, reason: string) => request<void>(`/kb/documents/${id}/reject`, json("POST", { actor, reason })),
  kbWithdraw: (id: number, actor: string, reason: string) => request<void>(`/kb/documents/${id}/withdraw`, json("POST", { actor, reason })),
  kbSearch: (body: { query: string; collections?: string[]; domain?: string; jurisdiction?: string; as_of?: string; k?: number }) =>
    request<KbHit[]>("/kb/search", json("POST", body)),
  kbAsk: (body: { question: string; asked_by: string; domain: string; jurisdiction: string }) =>
    request<GroundedAnswerResult>("/kb/ask", json("POST", body)),
  kbReviewQueue: () => request<ReviewQueueItem[]>("/kb/review-queue"),
  kbResolveReview: (id: number, body: { actor: string; role: string; outcome: string; resolution: string }) =>
    request<void>(`/kb/review-queue/${id}/resolve`, json("POST", body)),
  kbImpacts: (projectId?: number) => request<KbImpact[]>(`/kb/impacts${projectId ? `?project_id=${projectId}` : ""}`),
  kbResolveImpact: (id: number, actor: string, reason: string) => request<void>(`/kb/impacts/${id}/resolve`, json("POST", { actor, reason })),
};
