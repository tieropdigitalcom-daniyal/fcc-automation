import asyncio

import httpx
import pytest

from packages.oracle_connector.rest import AmbiguousSubmission, Capabilities, OracleClient, OracleError, build_job_url


async def no_sleep(_):
    pass


def run_client(handler, operation, capabilities=None):
    async def run():
        client = OracleClient("https://epm.example.com", "A/B", lambda: "synthetic-test-token",
                              capabilities, transport=httpx.MockTransport(handler), sleep=no_sleep)
        try:
            return await operation(client)
        finally:
            await client.close()
    return asyncio.run(run())


def test_documented_job_url():
    assert build_job_url("https://epm.example.com", "A/B", "123").endswith("/applications/A%2FB/jobs/123")
    with pytest.raises(ValueError): build_job_url("https://epm.example.com/internal", "a", "1")


@pytest.mark.parametrize("status,state", [(-1, "PENDING"), (0, "SUCCEEDED"), (1, "FAILED"), (2, "FAILED"), (3, "FAILED"), (4, "FAILED"), (2147483647, "FAILED")])
def test_async_status_contract(status, state):
    output = run_client(lambda request: httpx.Response(200, json={"jobID": "12", "status": status}), lambda client: client.poll_job("12"))
    assert output["state"] == state


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_failure_and_expired_token_block(status):
    with pytest.raises(OracleError, match="access denied"):
        run_client(lambda request: httpx.Response(status), lambda client: client.poll_job("1"))


def test_rate_limit_retry():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) < 3 else httpx.Response(200, json={"status": 0})
    assert run_client(handler, lambda client: client.poll_job("1"))["state"] == "SUCCEEDED"
    assert len(calls) == 3


def test_submission_contract_and_no_blind_retry():
    calls = []
    def handler(request):
        calls.append(request)
        assert b'"jobType":"EXPORT_DATA"' in request.content
        raise httpx.ReadTimeout("Synthetic timeout")
    with pytest.raises(AmbiguousSubmission):
        run_client(handler, lambda client: client.start_export("Approved", "run.zip"), Capabilities("test", True, ("Approved",)))
    assert len(calls) == 1


def test_unverified_export_unavailable():
    with pytest.raises(OracleError, match="tenant-verified"):
        run_client(lambda request: httpx.Response(200), lambda client: client.start_export("Any", "x.zip"))


@pytest.mark.parametrize("content,headers,size", [(b"short", {}, 10), (b'{}', {"Content-Type": "application/json"}, 2)])
def test_truncated_and_json_error_downloads(content, headers, size):
    with pytest.raises(OracleError):
        run_client(lambda request: httpx.Response(200, content=content, headers=headers), lambda client: client.download_artifact("outbox/x.zip", size))


def test_download_exact_content_and_path_encoding():
    def handler(request):
        assert "outbox%2Fx.zip" in str(request.url)
        return httpx.Response(200, content=b"complete", headers={"Content-Type": "application/zip"})
    assert run_client(handler, lambda client: client.download_artifact("outbox/x.zip", 8)) == b"complete"


def test_empty_application_inventory_cannot_verify_connection():
    with pytest.raises(OracleError):
        run_client(lambda request: httpx.Response(200, json={"items": []}), lambda client: client.test_connection())


def test_503_exhausts_bounded_retries():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    with pytest.raises(OracleError):
        run_client(handler, lambda client: client.poll_job("1"))
    assert len(calls) == 3


def test_journal_pagination_complete():
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json={"items": [{"label": "J1" if offset == 0 else "J2"}],
                            "count": 1, "offset": offset, "totalResults": 2, "hasMore": offset == 0})
    journals = run_client(handler, lambda client: client.journal_inventory(
        {"scenario": "Actual", "year": "FY26", "period": "Nov"}, ["J1", "J2"], page_size=1))
    assert [journal["label"] for journal in journals] == ["J1", "J2"]


@pytest.mark.parametrize("fault", ["offset", "truncated", "duplicate", "empty", "total"])
def test_incomplete_journal_pagination_blocks(fault):
    def handler(request):
        offset = int(request.url.params["offset"])
        payload = {"items": [{"label": "J1" if offset == 0 else "J2"}], "count": 1,
                   "offset": offset, "totalResults": 2, "hasMore": offset == 0}
        if fault == "offset": payload["offset"] = 10
        elif fault == "truncated": payload["hasMore"] = False
        elif fault == "duplicate" and offset: payload["items"] = [{"label": "J1"}]
        elif fault == "empty": payload.update(items=[], count=0, hasMore=True)
        elif fault == "total": payload["totalResults"] = 3
        return httpx.Response(200, json=payload)
    with pytest.raises(OracleError):
        run_client(handler, lambda client: client.journal_inventory(
            {"scenario": "Actual", "year": "FY26", "period": "Nov"}, ["J1", "J2"], page_size=1))
