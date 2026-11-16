"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  FileCheck2,
  FileClock,
  FileText,
  GitCompareArrows,
  Layers3,
  LayoutDashboard,
  Link2,
  LoaderCircle,
  LogOut,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  Users,
  X,
} from "lucide-react";
import {
  amount,
  api,
  date,
  member,
  type Batch,
  type Case,
  type Check as Control,
  type Dashboard,
  type Policy,
  type Run,
  type User,
} from "./api-client";

const navigation = [
  ["overview", "Overview", LayoutDashboard],
  ["runs", "Validation runs", Play],
  ["reconciliation", "Reconciliation", GitCompareArrows],
  ["exceptions", "Exceptions", CircleHelp],
  ["journals", "Journals", FileText],
  ["intercompany", "Intercompany", Layers3],
  ["currency", "Currency translation", SlidersHorizontal],
  ["history", "History", FileClock],
  ["sources", "Data & evidence", Database],
  ["reports", "Audit reports", FileCheck2],
  ["policies", "Mappings & policies", ShieldCheck],
  ["connections", "Connections", Link2],
  ["jobs", "Automation", Activity],
  ["administration", "Administration", Settings2],
] as const;

const descriptions: Record<string, string> = {
  overview: "A clear view of your close, down to the smallest difference.",
  runs: "Reconcile immutable source snapshots against an approved policy.",
  reconciliation:
    "Follow each balance from its original evidence to its exact result.",
  exceptions: "Assign, investigate and document every financial exception.",
  journals: "Inspect complete journal inventories and signed line balances.",
  intercompany:
    "Review reciprocal entities at the same currency and consolidation stage.",
  currency:
    "Inspect rate evidence, full precision and the approved rounding stage.",
  sources: "Import controlled extracts and preserve their original evidence.",
  reports:
    "Download reproducible results, calculations and source fingerprints.",
  policies:
    "Versioned mappings and calculation policies with independent approval.",
  connections: "Inspect the Oracle environment and verify authorized access.",
  jobs: "Monitor durable validation requests, schedules and notification delivery.",
  administration:
    "Manage scoped identities and inspect the attributable audit trail.",
  history:
    "Compare captured validations and investigate changes in exact amounts.",
};

function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.toLowerCase().replaceAll(" ", "-")}`}>
      <span />
      {value.replaceAll("_", " ")}
    </span>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <Layers3 size={28} />
      <p>{children}</p>
    </div>
  );
}
function CardTitle({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card-title">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export default function Workbench({ section }: { section: string }) {
  const [mode, setMode] = useState("demo");
  const [user, setUser] = useState<User | null>(null);
  const [profiles, setProfiles] = useState<User[]>([]);
  const [csrf, setCsrf] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Run | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<Control | null>(null);
  const [caseDetail, setCaseDetail] = useState<Case | null>(null);
  const [caseHistory, setCaseHistory] = useState<
    {
      actor: string;
      created: string;
      payload: { comment?: string; to?: string };
    }[]
  >([]);
  const [connection, setConnection] = useState<{
    mode: string;
    application: string;
    environment: string;
    origin: string;
    capabilities: { name: string; state: string }[];
  } | null>(null);
  const [jobs, setJobs] = useState<{
    mode: string;
    alert_configured: boolean;
    notifications: { run_id: string; state: string; attempts: number }[];
  } | null>(null);
  const [schedules, setSchedules] = useState<
    {
      id: string;
      name: string;
      enabled: boolean;
      interval_minutes: number;
      next_due: string;
    }[]
  >([]);
  const [audit, setAudit] = useState<{
    chain_valid: boolean;
    events: {
      sequence: number;
      actor: string;
      action: string;
      created: string;
      hash: string;
    }[];
  } | null>(null);
  const [compare, setCompare] = useState<Run | null>(null);

  useEffect(() => {
    api<{ mode: string }>("/config")
      .then((config) => {
        setMode(config.mode);
        if (config.mode === "demo")
          api<User[]>("/demo/users")
            .then(setProfiles)
            .catch((e) => setError(e.message));
      })
      .catch((e) => setError(e.message));
    api<{ user: User; csrf: string }>("/session")
      .then((session) => {
        setUser(session.user);
        setCsrf(session.csrf);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const refresh = useCallback(async () => {
    if (!user) return;
    const [summary, history, inputs, versions, people] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<Run[]>("/runs"),
      api<Batch[]>("/batches"),
      api<Policy[]>("/policies"),
      api<User[]>("/users"),
    ]);
    setDashboard(summary);
    setRuns(history);
    setBatches(inputs);
    setPolicies(versions);
    setUsers(people);
    setSelectedId((current) => current || history[0]?.id || "");
    if (section === "connections") setConnection(await api("/connections"));
    if (section === "jobs") {
      setJobs(await api("/jobs"));
      setSchedules(await api("/schedules"));
    }
    if (
      section === "administration" &&
      ["auditor", "integration_admin", "finance_approver"].includes(user.role)
    )
      setAudit(await api("/audit"));
  }, [user, section]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    if (!selectedId || !user) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let wasQueued = false;
    const load = async () => {
      try {
        const [run, issues] = await Promise.all([
          api<Run>(`/runs/${selectedId}`),
          api<Case[]>(`/exceptions?run_id=${selectedId}`),
        ]);
        if (active) {
          setSelected(run);
          setCases(issues);
          if (run.state === "QUEUED") {
            wasQueued = true;
            timer = setTimeout(load, 2000);
          } else if (wasQueued) {
            await refresh();
          }
        }
      } catch (e) {
        if (active)
          setError(
            e instanceof Error ? e.message : "Could not refresh validation",
          );
      }
    };
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [selectedId, user, notice, refresh]);
  useEffect(() => {
    setPage(0);
  }, [query, status, selectedId]);

  useEffect(() => {
    if (!detail && !caseDetail) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const controls = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), a[href], input, select, textarea",
        ) || [],
      );
    controls()[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDetail(null);
        setCaseDetail(null);
      }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previous?.focus();
    };
  }, [detail, caseDetail]);

  async function action(work: () => Promise<void>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      await refresh();
      setNotice(success);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }

  const checks = useMemo(() => {
    let list = selected?.result?.checks || [];
    if (section === "journals")
      list = list.filter((c) => /Journal/.test(c.rule));
    if (section === "intercompany")
      list = list.filter((c) => /Intercompany/.test(c.rule));
    if (section === "currency") list = list.filter((c) => c.rule === "fx");
    if (status !== "all") list = list.filter((c) => c.status === status);
    if (query)
      list = list.filter(
        (c) =>
          JSON.stringify(c.pov).toLowerCase().includes(query.toLowerCase()) ||
          c.rule.toLowerCase().includes(query.toLowerCase()),
      );
    return list;
  }, [selected, section, status, query]);
  const latest = selected || dashboard?.latest;
  const counts = latest?.counts || {};
  const checked = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const title =
    navigation.find((item) => item[0] === section)?.[1] || "Overview";
  const canRun =
    user &&
    ["analyst", "reviewer", "finance_approver", "integration_admin"].includes(
      user.role,
    );

  function runSelector() {
    return (
      <select
        aria-label="Selected validation run"
        value={selectedId}
        onChange={(e) => setSelectedId(e.target.value)}
      >
        {runs.length === 0 && <option value="">No validations</option>}
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {run.id.slice(0, 8)} · {run.state} · {date(run.created)}
          </option>
        ))}
      </select>
    );
  }

  function controlsTable() {
    return (
      <section className="card">
        <div className="table-toolbar">
          <div className="search">
            <Search size={17} />
            <input
              aria-label="Search controls"
              placeholder="Search entity, account or control"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select
            aria-label="Control status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Control / account</th>
                <th>Entity</th>
                <th>Currency</th>
                <th className="numeric">Source / expected</th>
                <th className="numeric">FCCS / actual</th>
                <th className="numeric">Exact difference</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {checks.slice(page * 12, page * 12 + 12).map((check, index) => (
                <tr key={check.fingerprint + index}>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setDetail(check)}
                    >
                      {member(check.pov, "account")}
                    </button>
                    <small>{check.rule}</small>
                  </td>
                  <td>{member(check.pov, "entity")}</td>
                  <td>{member(check.pov, "currency")}</td>
                  <td className="numeric">{amount(check.expected)}</td>
                  <td className="numeric">{amount(check.actual)}</td>
                  <td
                    className={`numeric ${check.status === "FAIL" ? "negative" : ""}`}
                  >
                    {amount(check.variance)}
                  </td>
                  <td>
                    <Badge value={check.status} />
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Inspect ${check.rule} ${member(check.pov, "account")}`}
                      onClick={() => setDetail(check)}
                    >
                      <ChevronRight size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {checks.length === 0 && <Empty>No controls match this view.</Empty>}
        <div className="pagination">
          <span>{checks.length} controls · Exact decimal values</span>
          <div>
            <button
              className="icon-button"
              aria-label="Previous page"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={17} />
            </button>
            <span>
              {page + 1} / {Math.max(1, Math.ceil(checks.length / 12))}
            </span>
            <button
              className="icon-button"
              aria-label="Next page"
              disabled={(page + 1) * 12 >= checks.length}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={17} />
            </button>
          </div>
        </div>
      </section>
    );
  }

  function runForm(schedule = false) {
    return (
      <form
        className="form-grid"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const body = {
            gl_id: form.get("gl_id"),
            fccs_id: form.get("fccs_id"),
            policy_id: form.get("policy_id"),
            ...(schedule
              ? {
                  name: form.get("name"),
                  interval_minutes: Number(form.get("interval")),
                }
              : {}),
          };
          action(
            async () => {
              const run = await api<Run>(
                schedule ? "/schedules" : "/runs",
                { method: "POST", body: JSON.stringify(body) },
                csrf,
              );
              if (!schedule) setSelectedId(run.id);
            },
            schedule
              ? "Validation schedule saved"
              : "Validation requested. Track its status below.",
          );
        }}
      >
        <label>
          Independent GL / TB
          <select name="gl_id" required>
            {batches
              .filter((b) => b.side === "GL")
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {b.id.slice(0, 6)}
                </option>
              ))}
          </select>
        </label>
        <label>
          FCCS snapshot
          <select name="fccs_id" required>
            {batches
              .filter((b) => b.side === "FCCS")
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {b.id.slice(0, 6)}
                </option>
              ))}
          </select>
        </label>
        <label>
          Mapping and calculation policy
          <select name="policy_id" required>
            {policies.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} · {p.approved_by ? "Approved" : "Pending approval"}
              </option>
            ))}
          </select>
        </label>
        {schedule && (
          <>
            <label>
              Schedule name
              <input
                name="name"
                required
                placeholder="November evidence recheck"
              />
            </label>
            <label>
              Interval in minutes
              <input
                name="interval"
                type="number"
                min="5"
                defaultValue="60"
                required
              />
            </label>
          </>
        )}
        <div className="form-action">
          <button
            className="primary"
            disabled={busy || !canRun || !batches.length}
          >
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Play size={16} />
            )}
            {schedule ? "Create schedule" : "Run validation"}
          </button>
        </div>
      </form>
    );
  }

  if (
    loading ||
    (user &&
      !error &&
      (!dashboard || (selectedId && selected?.id !== selectedId)))
  )
    return (
      <main className="loading">
        <LoaderCircle className="spin" />
        Loading secure workspace
      </main>
    );
  if (!user)
    return (
      <main className="login-page">
        <div className="login-brand">
          <div className="brand-icon">
            <Layers3 size={25} />
          </div>
          <span>
            FCCS<span className="muted"> / Assurance</span>
          </span>
        </div>
        <div className="login-card">
          <span className="eyebrow">FINANCIAL VALIDATION</span>
          <h1>
            Confidence in
            <br />
            every close.
          </h1>
          <p>
            Trace every balance. Investigate every difference. Keep the evidence
            together.
          </p>
          {error && (
            <div role="alert" className="alert error">
              {error}
            </div>
          )}
          {mode === "demo" ? (
            <>
              <div className="demo-note">
                <span className="dot" /> DEMO DATA · Synthetic local workspace
              </div>
              <label>
                Choose a demonstration profile
                <select id="demo-profile" defaultValue="demo-analyst">
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name} · {profile.role.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="primary full"
                disabled={busy || !profiles.length}
                onClick={() =>
                  action(async () => {
                    const id = (
                      document.getElementById(
                        "demo-profile",
                      ) as HTMLSelectElement
                    ).value;
                    const session = await api<{ user: User; csrf: string }>(
                      "/auth/demo",
                      { method: "POST", body: JSON.stringify({ user_id: id }) },
                    );
                    setUser(session.user);
                    setCsrf(session.csrf);
                  }, "Signed in to the synthetic workspace")
                }
              >
                Open workspace <ArrowRight size={17} />
              </button>
            </>
          ) : (
            <a className="primary full" href="/api/auth/login">
              Continue with enterprise SSO <ArrowRight size={17} />
            </a>
          )}
          <p className="login-foot">
            <ShieldCheck size={15} /> Read-only financial controls with
            attributable evidence
          </p>
        </div>
        <div className="login-art" aria-hidden="true">
          <div />
          <div />
          <div />
          <span>
            Precision.
            <br />
            With perspective.
          </span>
        </div>
      </main>
    );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <div className="brand-icon">
            <Layers3 size={22} />
          </div>
          <div>
            FCCS<span>Validation & Audit</span>
          </div>
        </Link>
        <div className="workspace">
          <span className="workspace-avatar">F</span>
          <div>
            Finance workspace<small>Consolidation controls</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {navigation.map(([id, label, Icon], index) => (
            <Link
              aria-label={label}
              title={label}
              className={`nav-item ${section === id ? "active" : ""} ${index === 8 ? "nav-divider" : ""}`}
              key={id}
              href={id === "overview" ? "/" : `/${id}`}
            >
              <Icon size={17} />
              <span>{label}</span>
              {id === "exceptions" && !!cases.length && <b>{cases.length}</b>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="environment">
            <span className="dot" />
            {mode === "demo"
              ? "Synthetic environment"
              : "Controlled environment"}
            <small>Read-only validation</small>
          </div>
          <button
            className="user-menu"
            onClick={() =>
              action(async () => {
                await api("/auth/logout", { method: "POST" }, csrf);
                setUser(null);
              }, "Signed out")
            }
          >
            <span className="avatar">
              {user.name
                .split(" ")
                .map((part) => part[0])
                .slice(0, 2)
                .join("")}
            </span>
            <span>
              {user.name}
              <small>{user.role.replaceAll("_", " ")}</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div>
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <span>{title}</span>
          </div>
          <div>
            {mode === "demo" && <span className="demo-pill">DEMO DATA</span>}
            <span className="read-only">
              <ShieldCheck size={14} />
              Read-only
            </span>
            <span className="avatar small-avatar">{user.name[0]}</span>
          </div>
        </header>
        <main className="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">FCCS ASSURANCE</div>
              <h1>{section === "overview" ? "Close overview" : title}</h1>
              <p>{descriptions[section]}</p>
            </div>
            <div className="heading-actions">
              {section !== "runs" && canRun && (
                <Link className="primary" href="/runs">
                  <Play size={15} />
                  Run validation
                </Link>
              )}
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <Check size={16} />
              {notice}
              <button
                aria-label="Dismiss message"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {[
            "overview",
            "reconciliation",
            "journals",
            "intercompany",
            "currency",
            "exceptions",
            "reports",
            "history",
          ].includes(section) && (
            <div className="scope-bar">
              <div>
                <span className="scope-label">VALIDATION</span>
                {runSelector()}
              </div>
              <span>
                <Clock3 size={15} />
                {latest?.completed
                  ? `Completed ${date(latest.completed)}`
                  : latest?.state === "QUEUED"
                    ? "Queued for validation"
                    : "Choose a completed run"}
              </span>
            </div>
          )}

          {section === "overview" && (
            <>
              <section
                className={`outcome ${latest?.state === "PASS" ? "clean" : ""}`}
              >
                <div className="outcome-icon">
                  <ShieldCheck size={25} />
                </div>
                <div>
                  <h2>
                    {latest
                      ? latest.state === "QUEUED"
                        ? "Validation queued"
                        : latest.state === "PASS"
                          ? "Declared scope reconciled"
                          : latest.state === "BLOCKED"
                            ? "Coverage needs attention"
                            : "Your close needs a closer look"
                      : "Start your first validation"}
                  </h2>
                  <p>
                    {latest
                      ? latest.state === "QUEUED"
                        ? "Waiting for a worker. Results will refresh automatically when processing completes."
                        : `${counts.FAIL || 0} failed checks and ${counts.BLOCKED || 0} blocked checks in the selected evidence scope.`
                      : "Import independent source and FCCS evidence to begin."}
                  </p>
                </div>
                {latest && <Badge value={latest.state} />}
                <Link href="/exceptions" className="text-button">
                  Review exceptions <ArrowRight size={16} />
                </Link>
              </section>
              <div className="metrics">
                <div className="metric">
                  <span>
                    Controls evaluated
                    <Layers3 size={17} />
                  </span>
                  <strong>{checked}</strong>
                  <small>
                    {dashboard?.entities.length || 0} entities in scope
                  </small>
                </div>
                <div className="metric">
                  <span>
                    Passed checks
                    <Check size={17} />
                  </span>
                  <strong>{counts.PASS || 0}</strong>
                  <small>Evidence-backed control results</small>
                </div>
                <div className="metric">
                  <span>
                    Financial exceptions
                    <GitCompareArrows size={17} />
                  </span>
                  <strong className="negative">{counts.FAIL || 0}</strong>
                  <small>Every non-zero difference retained</small>
                </div>
                <div className="metric">
                  <span>
                    Coverage blockers
                    <ShieldCheck size={17} />
                  </span>
                  <strong>{counts.BLOCKED || 0}</strong>
                  <small>Missing evidence stops assurance</small>
                </div>
              </div>
              <div className="overview-grid">
                <section className="card">
                  <CardTitle
                    title="Control coverage"
                    subtitle="Results across the selected validation"
                    action={<Badge value={latest?.state || "QUEUED"} />}
                  />
                  <div className="coverage-content">
                    <div className="coverage-total">
                      <strong>{checked}</strong>
                      <span>evaluated controls</span>
                    </div>
                    <div className="stacked-bar">
                      {["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"].map(
                        (state) => (
                          <div
                            key={state}
                            className={state.toLowerCase()}
                            style={{
                              width: `${checked ? ((counts[state] || 0) / checked) * 100 : 0}%`,
                            }}
                          />
                        ),
                      )}
                    </div>
                    <div className="legend">
                      {["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"].map(
                        (state) => (
                          <div key={state}>
                            <span
                              className={`legend-dot ${state.toLowerCase()}`}
                            />
                            {state.replaceAll("_", " ")}
                            <b>{counts[state] || 0}</b>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                  <div className="card-footer">
                    <ShieldCheck size={16} /> Scope, precision and mappings
                    checked before comparison
                  </div>
                </section>
                <section className="card">
                  <CardTitle
                    title="Evidence at a glance"
                    subtitle="Original artifacts for the selected run"
                    action={
                      <Link href="/sources" className="text-button">
                        View all <ArrowRight size={15} />
                      </Link>
                    }
                  />
                  <div className="evidence-list">
                    {batches
                      .filter((batch) =>
                        [latest?.gl_id, latest?.fccs_id].includes(batch.id),
                      )
                      .map((batch) => (
                        <div key={batch.id}>
                          <div className="file-icon">
                            <FileText size={20} />
                          </div>
                          <div>
                            <strong>
                              {batch.side === "GL"
                                ? "Independent general ledger"
                                : "FCCS export snapshot"}
                            </strong>
                            <small>
                              {batch.row_count} records ·{" "}
                              {batch.entities.length} entities
                            </small>
                            <code>{batch.sha256.slice(0, 22)}…</code>
                          </div>
                          <Badge
                            value={
                              batch.manifest.complete
                                ? "RECEIVED"
                                : "INCOMPLETE"
                            }
                          />
                        </div>
                      ))}
                  </div>
                  <div className="card-footer">
                    <Database size={16} />
                    {dashboard?.database} · {dashboard?.oracle}
                  </div>
                </section>
              </div>
              <section className="card">
                <CardTitle
                  title="Exceptions requiring attention"
                  subtitle="Exact differences at individual financial intersections"
                  action={
                    <Link href="/exceptions" className="text-button">
                      Open workbench <ArrowRight size={15} />
                    </Link>
                  }
                />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Account / control</th>
                        <th>Entity</th>
                        <th>Currency</th>
                        <th className="numeric">Source value</th>
                        <th className="numeric">FCCS value</th>
                        <th className="numeric">Difference</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cases.slice(0, 5).map((item) => (
                        <tr key={item.id}>
                          <td>
                            <button
                              className="text-button"
                              onClick={() => setDetail(item.check)}
                            >
                              {member(item.check.pov, "account")}
                            </button>
                            <small>{item.check.rule}</small>
                          </td>
                          <td>{member(item.check.pov, "entity")}</td>
                          <td>{member(item.check.pov, "currency")}</td>
                          <td className="numeric">
                            {amount(item.check.expected)}
                          </td>
                          <td className="numeric">
                            {amount(item.check.actual)}
                          </td>
                          <td className="numeric negative">
                            {amount(item.check.variance)}
                          </td>
                          <td>
                            <Badge value={item.state} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!cases.length && (
                  <Empty>No exceptions in the selected run.</Empty>
                )}
              </section>
            </>
          )}

          {section === "runs" && (
            <>
              <section className="card">
                <CardTitle
                  title="Start a validation"
                  subtitle="Reprocessing identical inputs returns the original deterministic run."
                />
                {runForm()}
              </section>
              <section className="card">
                <CardTitle
                  title="Validation history"
                  subtitle={`${runs.length} captured runs`}
                />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th>Created</th>
                        <th>Scope</th>
                        <th>Result</th>
                        <th>Checks</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((run) => (
                        <tr key={run.id}>
                          <td>
                            <code>{run.id.slice(0, 12)}</code>
                          </td>
                          <td>{date(run.created)}</td>
                          <td>{run.entities.join(", ")}</td>
                          <td>
                            <Badge value={run.state} />
                          </td>
                          <td>
                            {Object.values(run.counts).reduce(
                              (a, b) => a + b,
                              0,
                            )}
                          </td>
                          <td>
                            <button
                              className="text-button"
                              onClick={() => {
                                setSelectedId(run.id);
                                setNotice(
                                  `Selected run ${run.id.slice(0, 12)}`,
                                );
                              }}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              {selected && controlsTable()}
            </>
          )}

          {["reconciliation", "journals", "intercompany", "currency"].includes(
            section,
          ) && (
            <>
              {section === "currency" && (
                <div className="info-note">
                  <ShieldCheck size={20} />
                  <p>
                    Rates and calculation parameters are tied to the approved
                    policy. Expand a control to inspect the unrounded amount,
                    rate precision and rounding stage.
                  </p>
                </div>
              )}
              {controlsTable()}
            </>
          )}

          {section === "sources" && (
            <>
              <section className="card">
                <CardTitle
                  title="Import financial evidence"
                  subtitle="Upload a ZIP containing data.csv and manifest.json, or a CSV with its source manifest."
                />
                <form
                  className="upload-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const form = new FormData(event.currentTarget);
                    action(async () => {
                      await api(
                        "/batches",
                        { method: "POST", body: form },
                        csrf,
                      );
                    }, "Evidence imported with original source fingerprint");
                  }}
                >
                  <label className="dropzone">
                    <Upload size={25} />
                    <strong>Select a source package</strong>
                    <span>UTF-8 CSV or ZIP · up to 20 MB</span>
                    <input
                      name="file"
                      aria-label="Source package"
                      type="file"
                      accept=".csv,.zip"
                      required
                    />
                  </label>
                  <label>
                    Source manifest for a CSV
                    <textarea
                      name="manifest"
                      placeholder="Paste the JSON source manifest when importing a CSV. ZIP packages include their manifest."
                      rows={5}
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      !["analyst", "integration_admin"].includes(user.role)
                    }
                  >
                    <Upload size={16} />
                    Import evidence
                  </button>
                </form>
              </section>
              <section className="card">
                <CardTitle
                  title="Source evidence"
                  subtitle={`${batches.length} immutable snapshots`}
                />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Snapshot</th>
                        <th>Source</th>
                        <th>Records</th>
                        <th>Extraction</th>
                        <th>Declared completeness</th>
                        <th>Original evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.map((batch) => (
                        <tr key={batch.id}>
                          <td>
                            <strong>{batch.name}</strong>
                            <small className="hash">
                              SHA-256 {batch.sha256}
                            </small>
                          </td>
                          <td>{batch.side}</td>
                          <td>{batch.row_count}</td>
                          <td>{date(batch.manifest.extracted_at)}</td>
                          <td>
                            <Badge
                              value={
                                batch.manifest.complete &&
                                batch.manifest.precision_verified
                                  ? "ATTESTED"
                                  : "INCOMPLETE"
                              }
                            />
                          </td>
                          <td>
                            <a
                              className="text-button"
                              href={`/api/batches/${batch.id}/evidence`}
                            >
                              <ArrowDownToLine size={16} />
                              Download
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}

          {section === "exceptions" && (
            <section className="card">
              <CardTitle
                title="Exception workbench"
                subtitle="Review actions retain the original financial outcome."
              />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Exception</th>
                      <th>Entity</th>
                      <th className="numeric">Exact difference</th>
                      <th>Owner</th>
                      <th>State</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {cases.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.check.rule}</strong>
                          <small>
                            {member(item.check.pov, "account")} ·{" "}
                            {item.check.explanation}
                          </small>
                        </td>
                        <td>{member(item.check.pov, "entity")}</td>
                        <td className="numeric negative">
                          {amount(item.check.variance)}{" "}
                          <small>{member(item.check.pov, "currency")}</small>
                        </td>
                        <td>
                          {users.find((person) => person.id === item.owner)
                            ?.name || "Unassigned"}
                        </td>
                        <td>
                          <Badge value={item.state} />
                        </td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => {
                              setCaseDetail(item);
                              api<typeof caseHistory>(
                                `/exceptions/${item.id}/history`,
                              )
                                .then(setCaseHistory)
                                .catch((e) => setError(e.message));
                            }}
                          >
                            Review <ArrowRight size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!cases.length && (
                <Empty>
                  {latest?.state === "QUEUED"
                    ? "Validation is queued. Exception review becomes available after processing."
                    : "No exceptions in this scope."}
                </Empty>
              )}
            </section>
          )}

          {section === "reports" && (
            <>
              <div className="report-grid">
                {[
                  [
                    "zip",
                    "Complete evidence bundle",
                    "Original sources, full JSON results, CSV checks, PDF summary and SHA-256 checksums.",
                  ],
                  [
                    "pdf",
                    "Audit summary",
                    "A printable summary of exceptions, scope and evidence fingerprints.",
                  ],
                  [
                    "csv",
                    "Control register",
                    "Every check and exact amount, with formula-safe spreadsheet export.",
                  ],
                  [
                    "json",
                    "Reproducible results",
                    "Full dimensional scope, original strings, calculation parameters and lineage.",
                  ],
                ].map(([extension, label, description]) => (
                  <section className="card report-card" key={extension}>
                    <div className="file-icon">
                      <FileCheck2 size={26} />
                    </div>
                    <h2>{label}</h2>
                    <p>{description}</p>
                    {selected?.result ? (
                      <a
                        className="secondary"
                        href={`/api/runs/${selected.id}/report/${extension}`}
                      >
                        <ArrowDownToLine size={16} />
                        Download {extension.toUpperCase()}
                      </a>
                    ) : (
                      <span>Choose a completed run</span>
                    )}
                  </section>
                ))}
              </div>
              {selected?.result && (
                <div className="info-note">
                  <ShieldCheck size={23} />
                  <div>
                    <strong>Reproducible result fingerprint</strong>
                    <code className="hash">
                      {selected.result.result_sha256}
                    </code>
                    <p>
                      Evidence exports and review actions are recorded in the
                      audit trail.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}

          {section === "policies" && (
            <>
              <section className="card">
                <CardTitle
                  title="Mapping and calculation versions"
                  subtitle="A separate finance approver activates each proposed version."
                />
                {policies.map((policy) => (
                  <div className="policy-row" key={policy.id}>
                    <div>
                      <strong>{policy.id}</strong>
                      <small>
                        Author {policy.author} ·{" "}
                        {policy.approved_by
                          ? `Approved by ${policy.approved_by}`
                          : "Awaiting approval"}
                      </small>
                      <code className="hash">{policy.sha256}</code>
                      <details>
                        <summary>Inspect mappings and precision policy</summary>
                        <pre>{JSON.stringify(policy.document, null, 2)}</pre>
                      </details>
                    </div>
                    <Badge
                      value={policy.approved_by ? "APPROVED" : "PENDING"}
                    />
                    {!policy.approved_by &&
                      user.role === "finance_approver" && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            action(async () => {
                              await api(
                                `/policies/${policy.id}/approve`,
                                { method: "POST" },
                                csrf,
                              );
                            }, "Policy independently approved")
                          }
                        >
                          Approve
                        </button>
                      )}
                  </div>
                ))}
              </section>
              {["analyst", "integration_admin"].includes(user.role) && (
                <section className="card">
                  <CardTitle
                    title="Propose a new policy"
                    subtitle="Use a new ID and the complete versioned policy schema."
                  />
                  <form
                    className="padded-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const data = new FormData(event.currentTarget);
                      action(async () => {
                        const document = JSON.parse(String(data.get("policy")));
                        await api(
                          "/policies",
                          { method: "POST", body: JSON.stringify(document) },
                          csrf,
                        );
                      }, "Policy proposed for independent approval");
                    }}
                  >
                    <label>
                      Policy JSON
                      <textarea
                        name="policy"
                        rows={8}
                        required
                        defaultValue={
                          policies[0]
                            ? JSON.stringify(
                                {
                                  ...policies[0].document,
                                  id: "proposed-policy-v2",
                                },
                                null,
                                2,
                              )
                            : ""
                        }
                      />
                    </label>
                    <button className="primary" disabled={busy}>
                      <Plus size={16} />
                      Propose version
                    </button>
                  </form>
                </section>
              )}
            </>
          )}

          {section === "connections" && connection && (
            <>
              <section className="card">
                <CardTitle
                  title="Oracle Financial Consolidation & Close"
                  subtitle="Server-side configuration and user-context OAuth"
                  action={<Badge value={connection.mode} />}
                />
                <div className="connection-grid">
                  <div>
                    <span>Application</span>
                    <strong>{connection.application}</strong>
                  </div>
                  <div>
                    <span>Environment</span>
                    <strong>{connection.environment.toUpperCase()}</strong>
                  </div>
                  <div>
                    <span>Tenant origin</span>
                    <strong>{connection.origin}</strong>
                  </div>
                  <div>
                    <span>Authentication</span>
                    <strong>OAuth 2.0 · Server-side secret reference</strong>
                  </div>
                </div>
                <div className="card-footer">
                  <button
                    className="primary"
                    disabled={busy || user.role !== "integration_admin"}
                    onClick={() =>
                      action(
                        async () => {
                          const result = await api<{
                            status: string;
                            message?: string;
                          }>("/connections/test", { method: "POST" }, csrf);
                          setNotice(
                            `${result.status} · ${result.message || "Application access verified"}`,
                          );
                          if (result.status === "BLOCKED")
                            throw new Error(result.message);
                        },
                        connection.mode === "MOCK ONLY"
                          ? "Mock connector tested. No Oracle connection was attempted."
                          : "Connection check completed. Export capabilities still require tenant verification.",
                      )
                    }
                  >
                    <Link2 size={16} />
                    Test configured connection
                  </button>
                </div>
              </section>
              <section className="card">
                <CardTitle
                  title="Capability inventory"
                  subtitle="Verified contracts and tenant access are tracked independently."
                />
                {connection.capabilities.map((capability) => (
                  <div className="policy-row" key={capability.name}>
                    <strong>{capability.name}</strong>
                    <Badge value={capability.state} />
                  </div>
                ))}
              </section>
              <div className="info-note">
                <ShieldCheck size={21} />
                <p>
                  Integration administrators configure ORACLE_BASE_URL,
                  ORACLE_APPLICATION and the approved token provider in the
                  server environment. Live exports require tenant verification.
                  Credentials stay on the server.
                </p>
              </div>
            </>
          )}

          {section === "jobs" && (
            <>
              <div className="metrics three">
                <div className="metric">
                  <span>
                    Processing mode
                    <Activity size={17} />
                  </span>
                  <strong className="word-value">
                    {jobs?.mode || "Loading"}
                  </strong>
                  <small>
                    {jobs?.mode === "inline"
                      ? "Local synchronous execution"
                      : "Celery and Redis"}
                  </small>
                </div>
                <div className="metric">
                  <span>
                    Queued validations
                    <Clock3 size={17} />
                  </span>
                  <strong>
                    {runs.filter((run) => run.state === "QUEUED").length}
                  </strong>
                  <small>Persisted before dispatch</small>
                </div>
                <div className="metric">
                  <span>
                    External alerts
                    <Link2 size={17} />
                  </span>
                  <strong className="word-value">
                    {jobs?.alert_configured ? "Configured" : "Unconfigured"}
                  </strong>
                  <small>Notification outbox is retained</small>
                </div>
              </div>
              <section className="card">
                <CardTitle
                  title="Validation schedules"
                  subtitle="Recheck selected immutable snapshots on an interval. Source freshness remains enforced."
                />
                {schedules.map((schedule) => (
                  <div className="policy-row" key={schedule.id}>
                    <div>
                      <strong>{schedule.name}</strong>
                      <small>
                        Every {schedule.interval_minutes} minutes · Next{" "}
                        {date(schedule.next_due)}
                      </small>
                    </div>
                    <Badge value={schedule.enabled ? "ACTIVE" : "DISABLED"} />
                    {schedule.enabled && user.role === "integration_admin" && (
                      <button
                        className="text-button"
                        onClick={() =>
                          action(async () => {
                            await api(
                              `/schedules/${schedule.id}`,
                              { method: "DELETE" },
                              csrf,
                            );
                          }, "Schedule disabled")
                        }
                      >
                        Disable
                      </button>
                    )}
                  </div>
                ))}
                {!schedules.length && (
                  <Empty>
                    No active schedules. Start the Compose worker and beat
                    services to enable durable scheduling.
                  </Empty>
                )}
                {user.role === "integration_admin" && runForm(true)}
              </section>
              <section className="card">
                <CardTitle title="Job and notification history" />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th>Validation state</th>
                        <th>Execution attempts</th>
                        <th>Notification</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((run) => (
                        <tr key={run.id}>
                          <td>
                            <code>{run.id.slice(0, 12)}</code>
                          </td>
                          <td>
                            <Badge value={run.state} />
                          </td>
                          <td>{run.attempts}</td>
                          <td>
                            {jobs?.notifications.find(
                              (item) => item.run_id === run.id,
                            )?.state || "Awaiting completion"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}

          {section === "history" && (
            <section className="card">
              <CardTitle
                title="Compare validation snapshots"
                subtitle="Compare exact source and FCCS amounts at the same financial intersection."
              />
              <div className="padded-form">
                <label>
                  Comparison run
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      if (!e.target.value) setCompare(null);
                      else
                        api<Run>(`/runs/${e.target.value}`)
                          .then(setCompare)
                          .catch((error) => setError(error.message));
                    }}
                  >
                    <option value="">Choose another validation</option>
                    {runs
                      .filter((run) => run.id !== selectedId)
                      .map((run) => (
                        <option key={run.id} value={run.id}>
                          {run.id.slice(0, 12)} · {run.state} ·{" "}
                          {date(run.created)}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              {compare ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Entity / account</th>
                        <th>Selected source</th>
                        <th>Previous source</th>
                        <th>Selected FCCS</th>
                        <th>Previous FCCS</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selected?.result?.checks || [])
                        .filter((check) => check.rule.startsWith("C04"))
                        .map((check) => {
                          const previous = compare.result?.checks.find(
                            (item) =>
                              item.rule === check.rule &&
                              JSON.stringify(item.pov) ===
                                JSON.stringify(check.pov),
                          );
                          return (
                            <tr key={check.fingerprint}>
                              <td>
                                {member(check.pov, "entity")} /{" "}
                                {member(check.pov, "account")}
                                <small>{member(check.pov, "currency")}</small>
                              </td>
                              <td className="numeric">
                                {amount(check.expected)}
                              </td>
                              <td className="numeric">
                                {amount(previous?.expected)}
                              </td>
                              <td className="numeric">
                                {amount(check.actual)}
                              </td>
                              <td className="numeric">
                                {amount(previous?.actual)}
                              </td>
                              <td>
                                <Badge
                                  value={
                                    !previous
                                      ? "MISSING"
                                      : previous.actual !== check.actual ||
                                          previous.expected !== check.expected
                                        ? "CHANGED"
                                        : "UNCHANGED"
                                  }
                                />
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty>
                  Choose a second captured run to inspect historical changes.
                </Empty>
              )}
            </section>
          )}

          {section === "administration" && (
            <>
              <section className="card">
                <CardTitle
                  title="People and entity access"
                  subtitle="Role permissions are enforced on the server for every action and download."
                />
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Person</th>
                        <th>Role</th>
                        <th>Entity scope</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((person) => (
                        <tr key={person.id}>
                          <td>
                            <strong>{person.name}</strong>
                            <small>{person.id}</small>
                          </td>
                          <td>{person.role.replaceAll("_", " ")}</td>
                          <td>
                            {person.entities.includes("*")
                              ? "All authorized entities"
                              : person.entities.join(", ")}
                          </td>
                          <td>
                            <Badge value="ACTIVE" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              {user.role === "integration_admin" && (
                <section className="card">
                  <CardTitle
                    title="Provision enterprise identity"
                    subtitle="Use the exact OIDC subject issued by your approved identity provider."
                  />
                  <form
                    className="form-grid"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const form = new FormData(event.currentTarget);
                      action(async () => {
                        await api(
                          "/users",
                          {
                            method: "POST",
                            body: JSON.stringify({
                              subject: form.get("subject"),
                              name: form.get("name"),
                              role: form.get("role"),
                              entities: String(form.get("entities"))
                                .split(",")
                                .map((s) => s.trim()),
                            }),
                          },
                          csrf,
                        );
                      }, "Scoped identity provisioned");
                    }}
                  >
                    <label>
                      OIDC subject
                      <input name="subject" required />
                    </label>
                    <label>
                      Display name
                      <input name="name" required />
                    </label>
                    <label>
                      Role
                      <select name="role">
                        {[
                          "viewer",
                          "analyst",
                          "reviewer",
                          "finance_approver",
                          "integration_admin",
                          "auditor",
                        ].map((role) => (
                          <option key={role}>{role}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Authorized entities
                      <input
                        name="entities"
                        required
                        placeholder="US100, GB200"
                      />
                    </label>
                    <button className="primary" disabled={busy}>
                      <Plus size={16} />
                      Provision user
                    </button>
                  </form>
                </section>
              )}
              {audit && (
                <section className="card">
                  <CardTitle
                    title="Audit trail"
                    subtitle="Append-only events with a verifiable SHA-256 chain"
                    action={
                      <Badge
                        value={
                          audit.chain_valid
                            ? "CHAIN VERIFIED"
                            : "INTEGRITY FAILURE"
                        }
                      />
                    }
                  />
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Event</th>
                          <th>Actor</th>
                          <th>Time</th>
                          <th>Fingerprint</th>
                        </tr>
                      </thead>
                      <tbody>
                        {audit.events.map((event) => (
                          <tr key={event.sequence}>
                            <td>{event.action}</td>
                            <td>{event.actor}</td>
                            <td>{date(event.created)}</td>
                            <td>
                              <code>{event.hash.slice(0, 24)}…</code>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>FCCS Validation & Audit Agent</span>
            <span>Exact decimals · Source lineage · Attributable review</span>
          </footer>
        </main>
      </div>

      {detail && (
        <div className="modal-backdrop" onClick={() => setDetail(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Financial control evidence"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="close-modal icon-button"
              aria-label="Close evidence"
              onClick={() => setDetail(null)}
            >
              <X />
            </button>
            <div className="eyebrow">CONTROL EVIDENCE</div>
            <h2>{detail.rule}</h2>
            <Badge value={detail.status} />
            <p>{detail.explanation}</p>
            <div className="amount-grid">
              <div>
                <span>Source / expected</span>
                <strong>{amount(detail.expected)}</strong>
              </div>
              <div>
                <span>FCCS / actual</span>
                <strong>{amount(detail.actual)}</strong>
              </div>
              <div>
                <span>Exact difference</span>
                <strong className={detail.status === "FAIL" ? "negative" : ""}>
                  {amount(detail.variance)}
                </strong>
              </div>
            </div>
            <h3>Complete point of view</h3>
            <dl className="pov-grid">
              {Object.entries(detail.pov).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>
                    {typeof value === "object" ? JSON.stringify(value) : value}
                  </dd>
                </div>
              ))}
            </dl>
            <h3>Source lineage</h3>
            {detail.lineage.map((ref, i) => (
              <div className="lineage" key={`${ref.record_id}-${i}`}>
                <strong>{ref.record_id}</strong>
                <span>Original line {ref.line}</span>
                <code className="hash">{ref.sha256}</code>
                <a
                  className="text-button"
                  href={`/api/batches/${ref.batch_id}/evidence`}
                >
                  Download original evidence <ArrowDownToLine size={14} />
                </a>
              </div>
            ))}
            {!detail.lineage.length && (
              <p>
                Scope-level control. Inspect the source manifests and policy.
              </p>
            )}
            <h3>Calculation parameters</h3>
            <pre>{JSON.stringify(detail.parameters, null, 2)}</pre>
            <small>Rule version {detail.rule_version}</small>
          </section>
        </div>
      )}

      {caseDetail && (
        <div className="modal-backdrop" onClick={() => setCaseDetail(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Review exception"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="close-modal icon-button"
              aria-label="Close review"
              onClick={() => setCaseDetail(null)}
            >
              <X />
            </button>
            <div className="eyebrow">EXCEPTION REVIEW</div>
            <h2>{caseDetail.check.rule}</h2>
            <p>{caseDetail.check.explanation}</p>
            <div className="review-amount">
              <strong>{amount(caseDetail.check.variance)}</strong>
              <span>
                {member(caseDetail.check.pov, "currency")} ·{" "}
                {member(caseDetail.check.pov, "entity")}
              </span>
              <Badge value={caseDetail.state} />
            </div>
            <button
              className="text-button"
              onClick={() => {
                setDetail(caseDetail.check);
                setCaseDetail(null);
              }}
            >
              Inspect original evidence <ArrowRight size={15} />
            </button>
            <form
              className="padded-form"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                action(async () => {
                  await api(
                    `/exceptions/${caseDetail.id}`,
                    {
                      method: "PATCH",
                      body: JSON.stringify({
                        owner: data.get("owner"),
                        state: data.get("state"),
                        comment: data.get("comment"),
                        version: caseDetail.version,
                        evidence_run_id: data.get("evidence") || null,
                      }),
                    },
                    csrf,
                  );
                  setCaseDetail(null);
                }, "Review recorded in the audit trail");
              }}
            >
              <label>
                Assigned owner
                <select name="owner" defaultValue={caseDetail.owner || user.id}>
                  {users
                    .filter((person) =>
                      ["analyst", "reviewer", "finance_approver"].includes(
                        person.role,
                      ),
                    )
                    .map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Review state
                <select
                  name="state"
                  defaultValue={
                    caseDetail.state === "NEW"
                      ? "ASSIGNED"
                      : caseDetail.state === "ASSIGNED"
                        ? "IN_REVIEW"
                        : caseDetail.state
                  }
                >
                  {["ASSIGNED", "IN_REVIEW", "RESOLVED", "ACCEPTED_RISK"].map(
                    (value) => (
                      <option key={value}>{value}</option>
                    ),
                  )}
                </select>
              </label>
              <label>
                Review note
                <textarea
                  name="comment"
                  rows={3}
                  required
                  minLength={3}
                  placeholder="Record the investigation, evidence and next action"
                />
              </label>
              <label>
                Replacement evidence for resolution
                <select name="evidence">
                  <option value="">Choose a passing replacement run</option>
                  {runs
                    .filter((run) => run.state === "PASS")
                    .map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.id.slice(0, 12)}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="primary"
                disabled={
                  busy ||
                  !["analyst", "reviewer", "finance_approver"].includes(
                    user.role,
                  )
                }
              >
                Save review
              </button>
            </form>
            <h3>Review history</h3>
            {caseHistory.length ? (
              caseHistory.map((event, i) => (
                <div className="history-note" key={i}>
                  <strong>
                    {event.actor} · {event.payload.to}
                  </strong>
                  <small>{date(event.created)}</small>
                  <p>{event.payload.comment}</p>
                </div>
              ))
            ) : (
              <p>No review actions yet.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
