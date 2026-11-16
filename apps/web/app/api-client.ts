export type User = {
  id: string;
  name: string;
  role: string;
  entities: string[];
  active: boolean;
};
export type POV = Record<string, string | Record<string, string>>;
export type Lineage = {
  batch_id: string;
  sha256: string;
  line: number;
  record_id: string;
};
export type Check = {
  rule: string;
  rule_version: string;
  status: string;
  explanation: string;
  pov: POV;
  expected: string | null;
  actual: string | null;
  variance: string | null;
  lineage: Lineage[];
  parameters: Record<string, unknown>;
  fingerprint: string;
};
export type Run = {
  id: string;
  state: string;
  entities: string[];
  created: string;
  completed: string | null;
  created_by: string;
  policy_id: string;
  gl_id: string;
  fccs_id: string;
  prior_id: string | null;
  counts: Record<string, number>;
  attempts: number;
  result?: {
    status: string;
    checks: Check[];
    result_sha256: string;
    policy_sha256: string;
  };
};
export type Batch = {
  id: string;
  name: string;
  side: string;
  sha256: string;
  created: string;
  entities: string[];
  row_count: number;
  manifest: {
    complete: boolean;
    precision_verified: boolean;
    extracted_at: string;
    policy_id: string;
    expected_povs: POV[];
    [key: string]: unknown;
  };
};
export type Case = {
  id: string;
  run_id: string;
  check: Check;
  state: string;
  owner: string | null;
  version: number;
};
export type Policy = {
  id: string;
  author: string;
  approved_by: string | null;
  sha256: string;
  document: Record<string, unknown>;
};
export type Dashboard = {
  latest: Run | null;
  runs: Run[];
  run_count: number;
  open_exceptions: number;
  entities: string[];
  storage: string;
  database: string;
  worker: string;
  oracle: string;
};

export async function api<T>(
  path: string,
  options: RequestInit = {},
  csrf = "",
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Service unavailable" }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Check the required fields and input schema",
    );
  }
  return response.json();
}

// Insert grouping separators directly into decimal strings. Never coerce money to Number.
export function amount(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Unavailable";
  const [integer, fraction] = value.split(".");
  return (
    integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (fraction !== undefined ? `.${fraction}` : "")
  );
}

export function member(pov: POV, name: string) {
  return typeof pov[name] === "string" ? (pov[name] as string) : "—";
}
export function date(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
