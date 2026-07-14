"""
Northwind CRM — a small fake SaaS product used as a stand-in for "a customer's
product" during local testing.

It intentionally includes the kinds of things a Forward Deployed Engineer runs
into when rolling an agent out to a real, unfamiliar product:
  - a login wall
  - a cookie-consent banner that blocks the page on first load
  - a "what's new" modal that appears asynchronously (after the page has
    already loaded) — the classic case that breaks naive "click and go" bots
  - a search box backed by a slow API call (loading state, not instant)
  - a multi-step settings wizard

None of this needs the network — it's plain Flask + server-rendered HTML,
run on localhost so the QA kit has something real to automate against.
"""
from flask import Flask, request, session, redirect, url_for, jsonify, render_template
import time

app = Flask(__name__)
app.secret_key = "demo-secret-not-for-production"

CONTACTS = [
    {"name": "Acme Corp", "owner": "Dana Lee", "stage": "Demo Scheduled"},
    {"name": "Acme Logistics", "owner": "Dana Lee", "stage": "Negotiation"},
    {"name": "Globex Inc", "owner": "Priya Nair", "stage": "Closed Won"},
    {"name": "Initech", "owner": "Sam Ortiz", "stage": "Prospecting"},
    {"name": "Umbrella Health", "owner": "Priya Nair", "stage": "Demo Scheduled"},
]


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username and password:
            session["user"] = username
            return redirect(url_for("dashboard"))
        error = "Enter both a username and password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"], active="dashboard")


@app.route("/contacts")
def contacts():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("contacts.html", user=session["user"], active="contacts")


@app.route("/api/contacts")
def api_contacts():
    if not session.get("user"):
        return jsonify({"error": "unauthorized"}), 401
    q = request.args.get("q", "").strip().lower()
    # Simulate a real backend call — not instant. This is why the QA kit has
    # to *wait for* the result rather than assume it's there immediately.
    time.sleep(1.1)
    results = [c for c in CONTACTS if q in c["name"].lower()] if q else CONTACTS
    return jsonify({"query": q, "count": len(results), "results": results})


@app.route("/settings")
def settings():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("settings.html", user=session["user"], active="settings")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
