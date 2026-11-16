"""Documented Oracle Cloud EPM contracts. Live capability validation is external."""
import asyncio
from dataclasses import dataclass
from urllib.parse import quote, urlsplit
import json

import httpx
from packages.reconciliation.contracts import digest


class OracleError(RuntimeError):
    pass


class AmbiguousSubmission(OracleError):
    """The server may have accepted a request. Operator reconciliation is required."""


def validate_origin(base):
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError("Oracle origin must be a clean configured HTTPS host")
    return base.rstrip("/")


def build_job_url(base, application, job_id):
    return f"{validate_origin(base)}/HyperionPlanning/rest/v3/applications/{quote(application, safe='')}/jobs/{quote(str(job_id), safe='')}"


@dataclass
class Capabilities:
    environment: str = "test"
    tenant_verified: bool = False
    approved_jobs: tuple[str, ...] = ()


class OracleClient:
    def __init__(self, base, application, token_provider, capabilities=None, transport=None, sleep=asyncio.sleep):
        self.base = validate_origin(base)
        self.application = application
        self.token_provider = token_provider
        self.capabilities = capabilities or Capabilities()
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=False, transport=transport)
        self.sleep = sleep

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, **kwargs):
        for attempt in range(3):
            token = self.token_provider()
            if not token:
                raise OracleError("Oracle OAuth user-context token is unavailable")
            try:
                response = await self.client.request(method, self.base + path,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if method != "GET":
                    raise AmbiguousSubmission("Export submission outcome is unknown. Reconcile Oracle jobs before retrying") from error
                if attempt == 2:
                    raise OracleError("Oracle read failed after bounded retries") from error
                await self.sleep(2 ** attempt)
                continue
            if response.status_code in {401, 403}:
                raise OracleError(f"Oracle access denied ({response.status_code}); coverage is BLOCKED")
            if response.status_code in {429, 502, 503, 504} and method == "GET" and attempt < 2:
                retry = response.headers.get("Retry-After", "")
                delay = min(int(retry), 30) if retry.isdigit() else 2 ** attempt
                await self.sleep(delay)
                continue
            if response.status_code >= 300:
                raise OracleError(f"Oracle HTTP request failed ({response.status_code})")
            return response
        raise OracleError("Oracle retry limit reached")

    async def test_connection(self):
        response = await self.request("GET", "/HyperionPlanning/rest/v3/applications")
        payload = response.json()
        if not any(item.get("name") == self.application for item in payload.get("items", [])):
            raise OracleError("Configured application is absent from the accessible application inventory")
        return {"status": "VERIFIED_APPLICATION_ACCESS", "application": self.application,
                "tenant_sha256": digest(self.base.encode()), "auth": "OAuth user context",
                "export_capabilities": "Require separate tenant verification"}

    async def poll_job(self, job_id):
        path = build_job_url(self.base, self.application, job_id).removeprefix(self.base)
        payload = (await self.request("GET", path)).json()
        status = payload.get("status")
        if type(status) is not int or status not in {-1, 0, 1, 2, 3, 4, 2147483647}:
            raise OracleError("Unrecognized Oracle job status")
        return {"job_id": str(payload.get("jobId", payload.get("jobID", job_id))),
                "status": status, "state": "SUCCEEDED" if status == 0 else "PENDING" if status == -1 else "FAILED"}

    async def start_export(self, job_name, filename):
        self.check_export(job_name)
        path = f"/HyperionPlanning/rest/v3/applications/{quote(self.application, safe='')}/jobs"
        payload = (await self.request("POST", path, json={"jobType": "EXPORT_DATA", "jobName": job_name,
                    "parameters": {"exportFileName": filename}})).json()
        identifier = payload.get("jobId", payload.get("jobID"))
        if identifier is None:
            raise AmbiguousSubmission("Oracle did not return an export job identifier")
        return {"job_id": str(identifier), "state": "SUBMITTED"}

    def check_export(self, job_name):
        if (self.capabilities.environment != "test" or not self.capabilities.tenant_verified
                or job_name not in self.capabilities.approved_jobs):
            raise OracleError("Export requires a tenant-verified non-production allowlist")

    async def list_files(self):
        payload = (await self.request("GET", "/interop/rest/v2/files/list")).json()
        if payload.get("status") != 0 or not isinstance(payload.get("items"), list):
            raise OracleError("Oracle file inventory is incomplete")
        return payload["items"]

    async def journal_inventory(self, filters, expected_labels, page_size=100):
        """Verify every inventory page against an independent approved label set."""
        if not {"scenario", "year", "period"}.issubset(filters) or not 1 <= page_size <= 1000:
            raise ValueError("Journal inventory requires scenario, year, period and a bounded page size")
        expected = set(expected_labels)
        if len(expected) != len(expected_labels):
            raise ValueError("Expected journal labels are duplicated")
        items, observed, offset = [], set(), 0
        path = f"/HyperionPlanning/rest/v3/applications/{quote(self.application, safe='')}/journals"
        for _ in range(1000):
            payload = (await self.request("GET", path, params={"q": json.dumps(filters), "offset": offset, "limit": page_size})).json()
            page = payload.get("items")
            if (not isinstance(page, list) or type(payload.get("hasMore")) is not bool
                    or payload.get("count") != len(page) or payload.get("offset") != offset
                    or payload.get("totalResults") != len(expected)):
                raise OracleError("Journal pagination or declared coverage is incomplete")
            for item in page:
                label = item.get("label")
                if not label or label in observed or label not in expected:
                    raise OracleError("Duplicate, missing or unexpected journal identity")
                observed.add(label)
            items.extend(page)
            if not payload["hasMore"]:
                if observed != expected:
                    raise OracleError("Journal inventory is missing required records")
                return items
            if not page:
                raise OracleError("Journal pagination made no progress")
            offset += len(page)
        raise OracleError("Journal pagination exceeded the safety bound")

    async def download_artifact(self, filename, expected_size, expected_hash=None):
        if type(expected_size) is not int or not 0 < expected_size <= 20_000_000:
            raise OracleError("A verified export size within the local 20 MB ingestion limit is required")
        path = f"/interop/rest/11.1.2.3.600/applicationsnapshots/{quote(filename, safe='')}/contents"
        # Stream and enforce the smaller application limit during retrieval.
        token = self.token_provider()
        if not token:
            raise OracleError("Oracle OAuth user-context token is unavailable")
        chunks, received = [], 0
        try:
            async with self.client.stream("GET", self.base + path, headers={"Authorization": f"Bearer {token}"}) as response:
                if response.status_code != 200 or "json" in response.headers.get("content-type", "").lower():
                    raise OracleError("Oracle download returned an error or access restriction")
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > expected_size:
                        raise OracleError("Oracle download exceeds its declared size")
                    chunks.append(chunk)
        except httpx.HTTPError as error:
            raise OracleError("Oracle download was interrupted; partial evidence rejected") from error
        data = b"".join(chunks)
        if len(data) != expected_size or expected_hash and digest(data) != expected_hash:
            raise OracleError("Oracle export is truncated or has an incorrect hash")
        return data


class MockConnector:
    def test_connection(self):
        return {"status": "MOCK_ONLY", "application": "FCCS_DEMO", "auth": "Synthetic fixture",
                "message": "No Oracle connection has been attempted"}
