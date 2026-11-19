import { NextRequest, NextResponse } from "next/server";
import initialDemoData from "../../demo-data.json";

// In-memory working state cloned from the seeded dataset
const state = {
  users: [...initialDemoData.users],
  policies: [...initialDemoData.policies],
  batches: [...initialDemoData.batches],
  runs: [...initialDemoData.runs],
  exceptions: [...initialDemoData.exceptions],
  schedules: [...initialDemoData.schedules],
  audit_events: [...initialDemoData.audit_events],
};

function getCurrentUser(req: NextRequest) {
  const sessionUser = req.cookies.get("fccs_session")?.value;
  if (!sessionUser) return null;
  return state.users.find((u) => u.id === sessionUser) || null;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const p = path.join("/");

  // 1. Config
  if (p === "config") {
    return NextResponse.json({
      mode: "demo",
      identity: "Demo profiles",
      storage: "local",
      queue: "inline",
      oracle_enabled: false,
    });
  }

  // 2. Demo Users
  if (p === "demo/users") {
    return NextResponse.json(state.users);
  }

  // 3. Current Session
  if (p === "session") {
    const user = getCurrentUser(req);
    if (!user) {
      return NextResponse.json(
        { detail: "Sign in required or session expired" },
        { status: 401 }
      );
    }
    return NextResponse.json({
      user,
      csrf: "demo-csrf-" + user.id,
    });
  }

  // 4. Dashboard
  if (p === "dashboard") {
    const latest = state.runs[0] || null;
    return NextResponse.json({
      latest,
      runs: state.runs.slice(0, 8),
      run_count: state.runs.length,
      open_exceptions: state.exceptions.filter(
        (e) => e.state !== "RESOLVED" && e.state !== "ACCEPTED_RISK"
      ).length,
      entities: ["GB200", "US100"],
      storage: "Local demo content store",
      database: "Supabase PostgreSQL / Next.js Demo",
      worker: "Inline worker (demo)",
      oracle: "MOCK ONLY",
    });
  }

  // 5. Runs
  if (p === "runs") {
    return NextResponse.json(state.runs);
  }

  if (p.startsWith("runs/")) {
    const parts = p.split("/");
    const runId = parts[1];

    if (parts.length === 2) {
      const run = state.runs.find((r) => r.id === runId);
      if (!run) {
        return NextResponse.json({ detail: "Run not found" }, { status: 404 });
      }
      return NextResponse.json(run);
    }

    if (parts.length === 4 && parts[2] === "report") {
      const format = parts[3];
      const run = state.runs.find((r) => r.id === runId);
      if (!run) {
        return NextResponse.json({ detail: "Run not found" }, { status: 404 });
      }
      if (format === "json") {
        return NextResponse.json(run.result || run);
      }
      if (format === "csv") {
        const rows = (run.result?.checks || []).map((c: any) =>
          `"${c.rule}","${c.status}","${c.variance || ""}","${c.explanation || ""}"`
        );
        const csv = ["Rule,Status,Variance,Explanation", ...rows].join("\n");
        return new NextResponse(csv, {
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition": `attachment; filename="audit-${runId.slice(0, 8)}.csv"`,
          },
        });
      }
      return NextResponse.json({ detail: "Format generated" });
    }
  }

  // 6. Batches
  if (p === "batches") {
    return NextResponse.json(state.batches);
  }

  // 7. Policies
  if (p === "policies") {
    return NextResponse.json(state.policies);
  }

  // 8. Users
  if (p === "users") {
    return NextResponse.json(state.users);
  }

  // 9. Exceptions
  if (p === "exceptions") {
    const runId = req.nextUrl.searchParams.get("run_id");
    if (runId) {
      return NextResponse.json(
        state.exceptions.filter((e) => e.run_id === runId)
      );
    }
    return NextResponse.json(state.exceptions);
  }

  // 10. Connections
  if (p === "connections") {
    return NextResponse.json({
      environment: "test",
      status: "ok",
      mode: "MOCK ONLY",
      application: "DEMO_FCCS",
      base_url: "https://demo.oraclecloud.com",
      last_test: new Date().toISOString(),
    });
  }

  // 11. Jobs & Schedules
  if (p === "jobs") {
    return NextResponse.json([]);
  }
  if (p === "schedules") {
    return NextResponse.json(state.schedules);
  }

  // 12. Audit events
  if (p === "audit") {
    return NextResponse.json(state.audit_events.slice(0, 100));
  }

  return NextResponse.json({ detail: `Route ${p} not found` }, { status: 404 });
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const p = path.join("/");

  // Demo Login
  if (p === "auth/demo") {
    const body = await req.json().catch(() => ({}));
    const userId = body.user_id || "demo-analyst";
    const user = state.users.find((u) => u.id === userId) || state.users[0];

    const res = NextResponse.json({
      user,
      csrf: "demo-csrf-" + user.id,
    });
    res.cookies.set("fccs_session", user.id, {
      path: "/",
      httpOnly: true,
      sameSite: "lax",
      maxAge: 86400,
    });
    return res;
  }

  // Logout
  if (p === "auth/logout") {
    const res = NextResponse.json({ ok: true });
    res.cookies.delete("fccs_session");
    return res;
  }

  // Trigger Validation Run
  if (p === "runs") {
    const body = await req.json().catch(() => ({}));
    const newRun = {
      ...state.runs[0],
      id: "run-" + Math.random().toString(36).substring(2, 10),
      created: new Date().toISOString(),
      created_by: "demo-analyst",
      counts: { PASS: 45, FAIL: 2, BLOCKED: 0 },
    };
    state.runs.unshift(newRun);
    return NextResponse.json(newRun);
  }

  // Test Oracle Connection
  if (p === "connections/test") {
    return NextResponse.json({
      status: "ok",
      mode: "MOCK ONLY",
      latency_ms: 42,
    });
  }

  return NextResponse.json({ ok: true });
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const p = path.join("/");

  if (p.startsWith("exceptions/")) {
    const caseId = p.split("/")[1];
    const body = await req.json().catch(() => ({}));
    const item = state.exceptions.find((e) => e.id === caseId);
    if (item) {
      if (body.state) item.state = body.state;
      if (body.owner) item.owner = body.owner;
      item.version = (item.version || 1) + 1;
      return NextResponse.json(item);
    }
  }

  return NextResponse.json({ ok: true });
}
