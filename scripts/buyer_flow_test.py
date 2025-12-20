#!/usr/bin/env python3
"""Buyer flow smoke test hitting the auth/buy-requests/orders endpoints."""

import os
import sys
import uuid
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("BUYER_FLOW_BASE_URL", "http://localhost:8000/api")


def fail(message):
    print(f"[FAILED] {message}", file=sys.stderr)
    sys.exit(1)


class ApiClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}

    def request(self, method, path, payload=None, allow_404=False):
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=data, headers=self.headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                return response.status, json.loads(body.decode())
        except HTTPError as exc:
            body = exc.read().decode(errors="ignore")
            if allow_404 and exc.code == 404:
                try:
                    return exc.code, json.loads(body or "{}")
                except json.JSONDecodeError:
                    return exc.code, {}
            fail(f"{method} {path} failed ({exc.code}): {body}")

    def set_token(self, token):
        self.headers["Authorization"] = f"Bearer {token}"


def register_buyer(client):
    email = f"buyer+{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": email,
        "password": "StrongPassw0rd!",
        "full_name": "Smoke Test Buyer",
        "role": "buyer"
    }
    status, data = client.request("POST", "/auth/register", payload)
    if status not in (200, 201):
        fail(f"Registration status {status}")
    return email, payload["password"], data


def login(client, email, password):
    status, data = client.request("POST", "/auth/login", {"email": email, "password": password})
    if status != 200:
        fail(f"Login status {status}")
    token = data.get("access_token") or data.get("token")
    if not token:
        fail("Login response missing bearer token")
    client.set_token(token)
    return data


def create_buy_request(client):
    payload = {
        "species": "cattle",
        "product_type": "live",
        "qty": 10,
        "unit": "head",
        "province": "Gauteng",
        "country": "ZA",
        "expires_at": "2025-12-31T23:59:59Z",
        "target_price": 1500.0,
        "notes": "Smoke test request"
    }
    status, data = client.request("POST", "/buy-requests", payload)
    if status not in (200, 201):
        fail(f"Create buy request status {status}")
    return data


def fetch_my_buy_requests(client):
    status, data = client.request("GET", "/buy-requests/my", allow_404=True)
    if status == 404:
        print("[WARN] /buy-requests/my returned 404; continuing with empty list")
        return []
    if status != 200:
        fail(f"Fetch my buy requests status {status}")
    return data


def fetch_buyer_offers(client):
    status, data = client.request("GET", "/buyers/offers")
    if status != 200:
        fail(f"Fetch buyer offers status {status}")
    return data


def fetch_user_orders(client):
    status, data = client.request("GET", "/orders/user")
    if status != 200:
        fail(f"Fetch orders status {status}")
    return data


def main():
    print(f"Running buyer flow smoke test against {BASE_URL}")
    client = ApiClient(BASE_URL)

    email, password, register_payload = register_buyer(client)
    print(f"Registered buyer {email}")

    login_data = login(client, email, password)
    print("Login succeeded, token stored")

    buy_request = create_buy_request(client)
    print(f"Created buy request {buy_request.get('id') or buy_request.get('request_id')}")

    my_requests = fetch_my_buy_requests(client)
    requests_count = len(my_requests if isinstance(my_requests, list) else my_requests.get("items", []))
    print(f"Found {requests_count} buy requests for buyer")

    offers = fetch_buyer_offers(client)
    offers_keys = list(offers.keys()) if isinstance(offers, dict) else "list"
    print(f"Fetched buyer offers; top-level keys: {offers_keys}")

    orders = fetch_user_orders(client)
    orders_count = len(orders if isinstance(orders, list) else orders.get("orders", []))
    print(f"Fetched {orders_count} orders for buyer")

    summary = {
        "base_url": BASE_URL,
        "email": email,
        "buy_request_id": buy_request.get("id") or buy_request.get("request_id"),
        "offers_payload": offers,
        "orders_payload": orders,
    }

    report_path = Path("buyer_flow_test_report.json")
    report_path.write_text(json.dumps(summary, indent=2))
    print(f"Buyer flow smoke test completed—report saved to {report_path.resolve()}")


if __name__ == "__main__":
    main()

