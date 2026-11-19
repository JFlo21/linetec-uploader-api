"""The /upload answer reports every inserted row, not the last page of 100.

Run from the repo root:  python -m pytest tests -q
(pytest is a development tool only; it is not in requirements.txt.)
No database is used: the connection and execute_values are replaced by fakes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import upload_server  # noqa: E402

PAGE_SIZE = 100  # psycopg2.extras.execute_values default page size


class FakeCursor:
    def __init__(self, existing):
        self._existing = existing
        self.rowcount = -1
        self.inserted = []

    def execute(self, query, params=None):
        self._last_select = "SELECT" in query

    def fetchall(self):
        return list(self._existing)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, existing):
        self.cursor_obj = FakeCursor(existing)
        self.committed = False

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        pass


def fake_execute_values(cursor, query, values):
    """Behave like psycopg2: rowcount is left at the size of the last page."""
    cursor.inserted.extend(values)
    last_page = len(values) % PAGE_SIZE or PAGE_SIZE
    cursor.rowcount = last_page


def make_rows(count):
    return [
        {
            "project_id": "P1",
            "work_order": "WO1",
            "work_request": "92761244",
            "district": "D1",
            "location_id": f"LOC{i}",
            "cu_code": f"CU{i}",
            "description": "line",
            "work_type": "A",
            "quantity": 1,
        }
        for i in range(count)
    ]


def post_upload(monkeypatch, rows, existing=()):
    connection = FakeConnection(existing)
    monkeypatch.setattr(upload_server, "get_db_connection", lambda: connection)
    monkeypatch.setattr(upload_server, "execute_values", fake_execute_values)
    response = upload_server.app.test_client().post("/upload", json=rows)
    return response, connection


# The six uploads from production on 2026-11-18 (lines sent), plus the page edges.
@pytest.mark.parametrize("sent", [401, 73, 270, 1036, 311, 647, 1, 100, 101, 200])
def test_upload_reports_every_inserted_row(monkeypatch, sent):
    response, connection = post_upload(monkeypatch, make_rows(sent))

    body = response.get_json()
    assert response.status_code == 200
    assert body["uploaded_count"] == sent
    assert body["rows_uploaded"] == sent
    assert body["total_received"] == sent
    assert len(connection.cursor_obj.inserted) == sent
    assert connection.committed is True


def test_upload_count_leaves_out_duplicates(monkeypatch):
    rows = make_rows(250)
    existing = [("LOC0", "CU0", "92761244", "A"), ("LOC1", "CU1", "92761244", "A")]

    response, connection = post_upload(monkeypatch, rows, existing)

    body = response.get_json()
    assert body["uploaded_count"] == 248
    assert body["duplicates_found"] == 2
    assert body["total_received"] == 250
    assert len(connection.cursor_obj.inserted) == 248
