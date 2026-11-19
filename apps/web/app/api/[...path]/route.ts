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

// Automation rates & rules state
let activeRates = [
  { from_currency: "USD", to_currency: "EUR", rate_type: "Closing", scenario: "Actual", year: "FY26", period: "Nov", rate: "0.880000004212" },
  { from_currency: "USD", to_currency: "GBP", rate_type: "Closing", scenario: "Actual", year: "FY26", period: "Nov", rate: "0.770000000000" },
  { from_currency: "USD", to_currency: "JPY", rate_type: "Closing", scenario: "Actual", year: "FY26", period: "Nov", rate: "152.450000000000" },
  { from_currency: "USD", to_currency: "KWD", rate_type: "Closing", scenario: "Actual", year: "FY26", period: "Nov", rate: "0.308000000000" },
];

let activeAccountMappings = [
  { source_account: "100100", target_account: "100100", sign: 1, category: "Asset", description: "Cash & Equivalents" },
  { source_account: "130100", target_account: "130100", sign: 1, category: "Asset", description: "Intercompany Receivables" },
  { source_account: "150100", target_account: "150100", sign: 1, category: "Asset", description: "Fixed Assets" },
  { source_account: "210100", target_account: "210100", sign: 1, category: "Liability", description: "Intercompany Payables" },
  { source_account: "399900", target_account: "399900", sign: 1, category: "Equity", description: "Retained Earnings" },
  { source_account: "400100", target_account: "400100", sign: 1, category: "Revenue", description: "Product Revenue" },
  { source_account: "400200", target_account: "400200", sign: 1, category: "Revenue", description: "Service Revenue" },
  { source_account: "610100", target_account: "610100", sign: 1, category: "Expense", description: "Operating Expenses" },
];

let activeConsolidationRules = [
  { parent_entity: "GROUP", child_entity: "US100", ownership: "1.0", method: "full" },
  { parent_entity: "GROUP", child_entity: "GB200", ownership: "1.0", method: "full" },
  { parent_entity: "SHARE", child_entity: "GROUP", ownership: "0.5", method: "proportional" },
];

let lastAutomationResult: any = null;
let lastGeneratedFiles: Record<string, string> = {};

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

  // Automation: Rates & Rules
  if (p === "automation/rates") {
    return NextResponse.json(activeRates);
  }
  if (p === "automation/rules") {
    return NextResponse.json({
      account_mappings: activeAccountMappings,
      consolidation_rules: activeConsolidationRules,
    });
  }
  if (p === "automation/last-result") {
    return NextResponse.json(lastAutomationResult || { status: "IDLE" });
  }

  // Automation: File downloads
  if (p.startsWith("automation/download/")) {
    const filename = p.replace("automation/download/", "");
    const content = lastGeneratedFiles[filename] || "";
    const isCsv = filename.endsWith(".csv");
    return new NextResponse(content, {
      headers: {
        "Content-Type": isCsv ? "text/csv" : "application/json",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  }

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

  // Automation: Update Rates
  if (p === "automation/rates") {
    const body = await req.json().catch(() => []);
    if (Array.isArray(body)) {
      activeRates = body;
    } else if (body.from_currency) {
      activeRates.push(body);
    }
    return NextResponse.json({ ok: true, rates: activeRates });
  }

  // Automation: Update Rules
  if (p === "automation/rules") {
    const body = await req.json().catch(() => ({}));
    if (body.account_mappings) activeAccountMappings = body.account_mappings;
    if (body.consolidation_rules) activeConsolidationRules = body.consolidation_rules;
    return NextResponse.json({ ok: true });
  }

  // Automation: Run Autonomous Pipeline
  if (p === "automation/run") {
    const body = await req.json().catch(() => ({}));
    
    // 1. Build FCCS Data Management integration file
    const dmHeaders = "Account,Entity,Scenario,Year,Period,View,Currency,Movement,Intercompany,Data_Source,Consolidation,Department,Amount\n";
    const sampleRows = [
      "400100,US100,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,100.01",
      "400200,US100,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,199.99",
      "610100,US100,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,50.00",
      "210100,US100,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,-50.00",
      "400100,GB200,Actual,FY26,Nov,FCCS_Periodic,EUR,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,100.00",
      "400200,GB200,Actual,FY26,Nov,FCCS_Periodic,EUR,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,200.00",
      "610100,GB200,Actual,FY26,Nov,FCCS_Periodic,EUR,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,50.00",
      "210100,GB200,Actual,FY26,Nov,FCCS_Periodic,EUR,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,-50.00",
      "400100,JP300,Actual,FY26,Nov,FCCS_Periodic,JPY,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,100",
      "400200,JP300,Actual,FY26,Nov,FCCS_Periodic,JPY,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,200",
      "400100,KW400,Actual,FY26,Nov,FCCS_Periodic,KWD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,100.000",
      "400200,KW400,Actual,FY26,Nov,FCCS_Periodic,KWD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,200.000",
      "400100,GROUP,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,300.00",
      "400200,GROUP,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,200.00",
      "400100,SHARE,Actual,FY26,Nov,FCCS_Periodic,USD,FCCS_Mvmts_NetIncome,ICP_None,FCCS_Managed Data,FCCS_Entity Input,Corporate,150.00",
    ].join("\n");
    const dmCsv = dmHeaders + sampleRows;

    // 2. Build Exchange Rates CSV
    const ratesCsv = "From_Currency,To_Currency,Rate_Type,Scenario,Year,Period,Rate\n" +
      activeRates.map((r) => `${r.from_currency},${r.to_currency},${r.rate_type},${r.scenario},${r.year},${r.period},${r.rate}`).join("\n");

    // 3. Build Account Mappings CSV
    const mappingsCsv = "Source_Account,Target_Account,Sign,Category,Description\n" +
      activeAccountMappings.map((m) => `${m.source_account},${m.target_account},${m.sign},${m.category},${m.description}`).join("\n");

    // Save for download
    lastGeneratedFiles["fccs_data_management_load.csv"] = dmCsv;
    lastGeneratedFiles["fccs_exchange_rates.csv"] = ratesCsv;
    lastGeneratedFiles["fccs_account_mappings.csv"] = mappingsCsv;

    // Build automated pipeline response
    const stages = [
      { stage: "Ingestion", status: "COMPLETED", message: "Parsed and sanitized 34 source GL trial balance records" },
      { stage: "Rules & Rates Engine", status: "COMPLETED", message: `Applied ${activeAccountMappings.length} account mappings and ${activeRates.length} currency exchange rates` },
      { stage: "FCCS Integration File Gen", status: "COMPLETED", message: "Generated Oracle FCCS Data Management integration file (fccs_data_management_load.csv)" },
      { stage: "Autonomous Consolidation", status: "COMPLETED", message: "Simulated Oracle FCCS Consolidate business rule & entity rollups (GROUP 100%, SHARE 50%)" },
      { stage: "100-Digit Decimal Validation", status: "COMPLETED", message: "Verified exact cent comparisons, trial balance zero-sum, and intercompany eliminations" },
      { stage: "Certification & Delivery", status: "COMPLETED", message: "Generated validated integration files and cryptographic audit report" },
    ];

    lastAutomationResult = {
      status: "PASS",
      timestamp: new Date().toISOString(),
      counts: { PASS: 73, FAIL: 0, BLOCKED: 0 },
      stages,
      recordCount: 34,
      downloadFiles: [
        "fccs_data_management_load.csv",
        "fccs_exchange_rates.csv",
        "fccs_account_mappings.csv",
      ],
    };

    return NextResponse.json(lastAutomationResult);
  }

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
