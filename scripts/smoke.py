"""Smoke-test the live AquiferAsk API."""

import argparse
import sys
import time

import httpx


def smoke_test(base_url: str, expected_version: str | None = None) -> bool:
    base_url = base_url.rstrip("/")

    for attempt in range(1, 31):
        try:
            with httpx.Client(timeout=15.0) as client:
                # 1. Check application health and version.
                health_response = client.get(f"{base_url}/health")
                health_response.raise_for_status()
                health = health_response.json()

                if health.get("status") != "ok":
                    raise RuntimeError("Health check did not return status=ok")

                version = health.get("version", "unknown")

                if expected_version and version != expected_version:
                    print(f"waiting: /health -> 200, old version {version}")
                    time.sleep(10)
                    continue

                print(f"ok   /health -> 200, version {version}")

                # 2. Check database readiness.
                ready_response = client.get(f"{base_url}/ready")
                ready_response.raise_for_status()
                ready = ready_response.json()

                if (
                    ready.get("status") != "ready"
                    or ready.get("checks", {}).get("database") is not True
                ):
                    raise RuntimeError(f"Database is not ready: {ready}")

                print(f"ok   /ready -> 200 {ready}")

                # 3. Check the documents API.
                docs_response = client.get(
                    f"{base_url}/v1/documents",
                    params={"limit": 1},
                )
                docs_response.raise_for_status()
                documents = docs_response.json()

                if not isinstance(documents.get("total"), int) or not isinstance(
                    documents.get("items"), list
                ):
                    raise RuntimeError("Unexpected documents API response")

                print("ok   /v1/documents?limit=1 -> 200")
                print("Smoke test passed")
                return True

        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            print(f"waiting: attempt {attempt}/30 - {error}")

        if attempt < 30:
            time.sleep(10)

    print("Smoke test failed: live application did not become ready")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AquiferAsk live smoke test")
    parser.add_argument("url", help="Base URL of the live application")
    parser.add_argument("--expect-version", help="Expected Git commit SHA")
    args = parser.parse_args()

    sys.exit(0 if smoke_test(args.url, args.expect_version) else 1)
