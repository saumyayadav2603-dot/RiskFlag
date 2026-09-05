from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import csv
import io
import json
import sqlite3

ROOT = Path(__file__).parent
DATABASE = ROOT / "data" / "feedback.db"


def connect_database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_feedback (
            transaction_id TEXT PRIMARY KEY,
            score INTEGER NOT NULL,
            evidence TEXT NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('confirmed', 'clear')),
            note TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def read_feedback():
    with connect_database() as connection:
        rows = connection.execute(
            "SELECT transaction_id, score, evidence, decision, note, reviewed_at "
            "FROM review_feedback ORDER BY reviewed_at"
        ).fetchall()
    return {
        row["transaction_id"]: {
            "transactionId": row["transaction_id"],
            "score": row["score"],
            "evidence": row["evidence"],
            "decision": row["decision"],
            "note": row["note"],
            "reviewedAt": row["reviewed_at"],
        }
        for row in rows
    }


class RiskFlagHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/feedback":
            self.send_json(read_feedback())
            return
        if self.path == "/api/feedback.csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["transaction_id", "score", "evidence", "decision", "note", "reviewed_at"],
            )
            writer.writeheader()
            writer.writerows(
                {
                    "transaction_id": item["transactionId"],
                    "score": item["score"],
                    "evidence": item["evidence"],
                    "decision": item["decision"],
                    "note": item["note"],
                    "reviewed_at": item["reviewedAt"],
                }
                for item in read_feedback().values()
            )
            body = output.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=riskflag-review-feedback.csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/feedback":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            required = {"transactionId", "score", "evidence", "decision", "note", "reviewedAt"}
            if not required.issubset(payload) or payload["decision"] not in {"confirmed", "clear"}:
                raise ValueError("invalid feedback payload")
            with connect_database() as connection:
                connection.execute(
                    """
                    INSERT INTO review_feedback
                        (transaction_id, score, evidence, decision, note, reviewed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(transaction_id) DO UPDATE SET
                        score=excluded.score,
                        evidence=excluded.evidence,
                        decision=excluded.decision,
                        note=excluded.note,
                        reviewed_at=excluded.reviewed_at
                    """,
                    (
                        payload["transactionId"],
                        int(payload["score"]),
                        payload["evidence"],
                        payload["decision"],
                        payload["note"],
                        payload["reviewedAt"],
                    ),
                )
            self.send_json(payload, status=201)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json({"error": str(error)}, status=400)

    def do_DELETE(self):
        if self.path != "/api/feedback":
            self.send_error(404)
            return
        with connect_database() as connection:
            connection.execute("DELETE FROM review_feedback")
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    connect_database().close()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), RiskFlagHandler)
    print("RiskFlag running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RiskFlag")
        server.server_close()
