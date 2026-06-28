import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CheckCircle2, Download, FileUp, Lock, Search, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import "./styles.css";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname || "localhost"}:8010/api`;

type User = {
  email: string;
  first_name: string;
  role: string;
  organization: { name: string; slug: string };
};

type Finding = { id: number; code: string; severity: "info" | "warning" | "error"; message: string };
type ActivityRecord = {
  id: number;
  source_type: string;
  source_name: string;
  activity_type: string;
  scope_category: string;
  normalized_quantity: string | null;
  normalized_unit: string;
  original_quantity: string | null;
  original_unit: string;
  period_start: string | null;
  period_end: string | null;
  location_code: string;
  location_name: string;
  status: string;
  confidence_score: number;
  metadata: Record<string, unknown>;
  raw_payload: Record<string, unknown>;
  findings: Finding[];
  locked_at: string | null;
};
type Batch = {
  id: number;
  source_type: string;
  filename: string;
  status: string;
  received_count: number;
  normalized_count: number;
  failed_count: number;
  suspicious_count: number;
  started_at: string;
};

function api(token: string | null, path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Token ${token}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

function App() {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState<User | null>(null);
  const [records, setRecords] = useState<ActivityRecord[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [dashboard, setDashboard] = useState<any>(null);
  const [selected, setSelected] = useState<ActivityRecord | null>(null);
  const [filters, setFilters] = useState({ source: "", status: "", severity: "" });
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = async () => {
    if (!token) return;
    setIsLoading(true);
    const [me, dash, recs, imports] = await Promise.all([
      api(token, "/auth/me/"),
      api(token, "/dashboard/"),
      api(token, `/activity-records/?${new URLSearchParams(filters as any)}`),
      api(token, "/imports/"),
    ]);
    if (me.ok) setUser(await me.json());
    if (dash.ok) setDashboard(await dash.json());
    if (recs.ok) setRecords(await recs.json());
    if (imports.ok) setBatches(await imports.json());
    setIsLoading(false);
  };

  useEffect(() => {
    load();
  }, [token, filters.source, filters.status, filters.severity]);

  if (!token) return <AuthScreen onToken={setToken} />;

  const statusCounts = dashboard?.status_counts || {};
  const cleanPendingIds = records.filter((r) => r.status === "pending_review" && !r.findings.some((f) => f.severity === "error")).map((r) => r.id);

  const upload = async (source_type: string, file: File) => {
    const body = new FormData();
    body.append("source_type", source_type);
    body.append("file", file);
    const response = await api(token, "/imports/upload/", { method: "POST", body });
    setMessage(response.ok ? "Import completed. Review queue updated." : `Import failed: ${await response.text()}`);
    await load();
  };

  const recordAction = async (record: ActivityRecord, action: "approve" | "reject" | "lock") => {
    const response = await api(token, `/activity-records/${record.id}/${action}/`, { method: "POST", body: JSON.stringify({ notes: "Reviewed in dashboard." }) });
    setMessage(response.ok ? `${action} succeeded.` : await response.text());
    await load();
    setSelected(response.ok ? await response.json() : record);
  };

  const bulkApprove = async () => {
    const response = await api(token, "/activity-records/bulk_approve/", { method: "POST", body: JSON.stringify({ ids: cleanPendingIds }) });
    setMessage(response.ok ? `Bulk approved ${cleanPendingIds.length} clean rows.` : await response.text());
    await load();
  };

  const exportLocked = async () => {
    const response = await api(token, "/export/locked/");
    if (!response.ok) {
      setMessage(`Export failed: ${await response.text()}`);
      return;
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "locked-audit-records.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><ShieldCheck size={22} /> Breathe ESG</div>
        <div className="tenant">{user?.organization?.name || "Loading organization"}</div>
        <nav>
          <a href="#dashboard">Dashboard</a>
          <a href="#upload">Upload</a>
          <a href="#review">Review Queue</a>
          <button className="nav-button" onClick={exportLocked}>Audit CSV</button>
        </nav>
        <button className="ghost" onClick={() => { localStorage.removeItem("token"); setToken(null); }}>Sign out</button>
      </aside>
      <main>
        <header className="topbar">
          <div>
            {isLoading && <p className="eyebrow">Refreshing data…</p>}
            <p className="eyebrow">Analyst review workspace</p>
            <h1>Normalize, review, approve, lock.</h1>
          </div>
          <button className="download" onClick={exportLocked}><Download size={16} /> Export locked rows</button>
        </header>

        {message && <div className="notice">{message}</div>}

        <section id="dashboard" className="metrics">
          <Metric label="Received rows" value={dashboard?.batch_counts?.received_rows || 0} />
          <Metric label="Failed rows" value={dashboard?.batch_counts?.failed_rows || 0} tone="bad" />
          <Metric label="Suspicious rows" value={dashboard?.batch_counts?.suspicious_rows || 0} tone="warn" />
          <Metric label="Pending review" value={statusCounts.pending_review || 0} />
          <Metric label="Approved" value={statusCounts.approved || 0} tone="good" />
          <Metric label="Locked audit rows" value={statusCounts.locked || 0} tone="good" />
        </section>

        <section id="upload" className="panel">
          <div className="section-title">
            <h2>Upload source data</h2>
            <p>SAP CSV, Green Button XML, or Concur-style itinerary JSON.</p>
            <p>Files are attached to each review row for traceability.</p>
          </div>
          <div className="upload-grid">
            {[
              ["sap", "SAP fuel/procurement CSV"],
              ["utility", "Utility Green Button XML"],
              ["travel", "Concur-style travel JSON"],
            ].map(([type, label]) => (
              <label className="upload-card" key={type}>
                <FileUp size={22} />
                <span>{label}</span>
                <input accept=".csv,.xml,.json" type="file" onChange={(event) => event.target.files?.[0] && upload(type, event.target.files[0])} />
              </label>
            ))}
          </div>
        </section>

        <section id="review" className="panel">
          <div className="section-title row">
            <div>
              <h2>Review queue</h2>
              <p>Raw source data stays attached to every normalized row.</p>
            </div>
            <button disabled={!cleanPendingIds.length} onClick={bulkApprove}><CheckCircle2 size={16} /> Bulk approve clean</button>
          </div>
          <div className="filters">
            <Search size={16} />
            <select value={filters.source} onChange={(e) => setFilters({ ...filters, source: e.target.value })}>
              <option value="">All sources</option><option value="sap">SAP</option><option value="utility">Utility</option><option value="travel">Travel</option>
            </select>
            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
              <option value="">All statuses</option><option value="pending_review">Pending</option><option value="suspicious">Suspicious</option><option value="approved">Approved</option><option value="locked">Locked</option><option value="rejected">Rejected</option>
              <option value="failed">Failed</option>
            </select>
            <select value={filters.severity} onChange={(e) => setFilters({ ...filters, severity: e.target.value })}>
              <option value="">All severities</option><option value="warning">Warning</option><option value="error">Error</option>
            </select>
          </div>
          <div className="table">
            <div className="table-head"><span>Source</span><span>Activity</span><span>Period</span><span>Quantity</span><span>Findings</span><span>Status</span></div>
            {records.map((record) => (
              <button className="table-row" key={record.id} onClick={() => setSelected(record)}>
                <span className="pill">{record.source_type}</span>
                <span>{record.activity_type}<small>{record.location_name || record.location_code}</small></span>
                <span>{record.period_start || "?"} to {record.period_end || "?"}</span>
                <span>{record.normalized_quantity || "?"} {record.normalized_unit}</span>
                <span>{record.findings.length ? <FindingSummary findings={record.findings} /> : "Clean"}</span>
                <span className={`status ${record.status}`}>{record.status.replace("_", " ")}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="section-title"><h2>Import timeline</h2><p>Every upload is tracked as a batch.</p></div>
          <div className="timeline">
            {batches.map((batch) => <div key={batch.id}><b>{batch.source_type}</b> {batch.filename} - {batch.received_count} rows - {batch.failed_count} failed - {batch.suspicious_count} suspicious</div>)}
          </div>
        </section>
      </main>

      {selected && (
        <DetailDrawer
          token={token}
          record={selected}
          onClose={() => setSelected(null)}
          onSaved={async (record) => {
            setSelected(record);
            await load();
            setMessage("Normalized row saved with an audit event.");
          }}
          onAction={recordAction}
        />
      )}
    </div>
  );
}

function AuthScreen({ onToken }: { onToken: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("analyst@acme.example");
  const [password, setPassword] = useState("BreatheDemo123!");
  const [org, setOrg] = useState("Acme Manufacturing");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    setLoading(true);
    setMessage("");
    try {
      const path = mode === "login" ? "/auth/login/" : "/auth/signup/";
      const body = mode === "login" ? { email, password } : { email, password, organization_name: org, full_name: "Analyst" };
      const response = await api(null, path, { method: "POST", body: JSON.stringify(body) });
      if (!response.ok) {
        const text = await response.text();
        return setMessage(text || `Login failed with HTTP ${response.status}.`);
      }
      const data = await response.json();
      localStorage.setItem("token", data.token);
      onToken(data.token);
    } catch (error) {
      setMessage(`Could not reach the API at ${API_BASE}. Start the Django server with: python backend/manage.py runserver 127.0.0.1:8010`);
    } finally {
      setLoading(false);
    }
  };
  return (
    <main className="auth">
      <section className="auth-panel">
        <div className="brand"><ShieldCheck size={24} /> Breathe ESG</div>
        <h1>Analyst sign-off for messy ESG data.</h1>
        <div className="segmented"><button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Login</button><button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Sign up</button></div>
        {mode === "signup" && <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="Organization" />}
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
        <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" type="password" />
        <button disabled={loading} onClick={submit}>{loading ? "Connecting..." : "Continue"}</button>
        {message && <p className="error">{message}</p>}
      </section>
    </main>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function FindingSummary({ findings }: { findings: Finding[] }) {
  const hasError = findings.some((f) => f.severity === "error");
  return <span className={hasError ? "finding error" : "finding warning"}>{hasError ? <XCircle size={15} /> : <TriangleAlert size={15} />} {findings.length}</span>;
}

function DetailDrawer({
  token,
  record,
  onClose,
  onAction,
  onSaved,
}: {
  token: string;
  record: ActivityRecord;
  onClose: () => void;
  onAction: (record: ActivityRecord, action: "approve" | "reject" | "lock") => void;
  onSaved: (record: ActivityRecord) => void;
}) {
  const canApprove = !["approved", "locked"].includes(record.status);
  const canLock = record.status === "approved";
  const [draft, setDraft] = useState({
    normalized_quantity: record.normalized_quantity || "",
    normalized_unit: record.normalized_unit || "",
    scope_category: record.scope_category,
    location_name: record.location_name || "",
  });
  const save = async () => {
    const response = await api(token, `/activity-records/${record.id}/`, {
      method: "PATCH",
      body: JSON.stringify(draft),
    });
    if (response.ok) onSaved(await response.json());
  };
  return (
    <aside className="drawer">
      <button className="ghost close" onClick={onClose}>Close</button>
      <h2>{record.activity_type}</h2>
      <p className="muted">{record.source_name} · confidence {record.confidence_score}%</p>
      <div className="drawer-actions">
        <button disabled={!canApprove || record.findings.some((f) => f.severity === "error")} onClick={() => onAction(record, "approve")}><CheckCircle2 size={16} /> Approve</button>
        <button disabled={record.status === "locked"} onClick={() => onAction(record, "reject")}><XCircle size={16} /> Reject</button>
        <button disabled={!canLock} onClick={() => onAction(record, "lock")}><Lock size={16} /> Lock</button>
      </div>
      <h3>Findings</h3>
      {record.findings.length ? record.findings.map((f) => <div className={`finding-line ${f.severity}`} key={f.id}><b>{f.code}</b><span>{f.message}</span></div>) : <p>Clean row. No findings.</p>}
      <h3>Normalized row</h3>
      <div className="edit-grid">
        <label>Quantity<input value={draft.normalized_quantity} disabled={record.status === "locked"} onChange={(e) => setDraft({ ...draft, normalized_quantity: e.target.value })} /></label>
        <label>Unit<input value={draft.normalized_unit} disabled={record.status === "locked"} onChange={(e) => setDraft({ ...draft, normalized_unit: e.target.value })} /></label>
        <label>Scope<select value={draft.scope_category} disabled={record.status === "locked"} onChange={(e) => setDraft({ ...draft, scope_category: e.target.value })}><option value="scope_1">Scope 1</option><option value="scope_2">Scope 2</option><option value="scope_3">Scope 3</option><option value="unknown">Unknown</option></select></label>
        <label>Location<input value={draft.location_name} disabled={record.status === "locked"} onChange={(e) => setDraft({ ...draft, location_name: e.target.value })} /></label>
      </div>
      <button disabled={record.status === "locked"} onClick={save}>Save normalized fields</button>
      <pre>{JSON.stringify({
        scope: record.scope_category,
        quantity: `${record.normalized_quantity} ${record.normalized_unit}`,
        period: [record.period_start, record.period_end],
        location: [record.location_code, record.location_name],
        metadata: record.metadata,
      }, null, 2)}</pre>
      <h3>Raw source payload</h3>
      <pre>{JSON.stringify(record.raw_payload, null, 2)}</pre>
    </aside>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
