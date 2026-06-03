"""
Pre-deploy validation script. Run before every Replit deploy:
  python tests/predeploy.py

Exits with code 1 if any check fails.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"

errors: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'[PASS]' if ok else '[FAIL]'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        errors.append(f"{name}: {detail}")


# ── Config files ──────────────────────────────────────────────────────────────

replit = (ROOT / ".replit").read_text()
check("gunicorn in .replit run command",   "gunicorn" in replit)
check("--timeout in .replit run command",  "--timeout" in replit)
check("gevent in .replit run command",     "gevent" in replit or "gthread" in replit)
check("waitForPort matches bind port",
      all(p in replit for p in ["5050"]),
      "ensure port 5050 is consistent")

req = (ROOT / "requirements.txt").read_text()
check("gunicorn in requirements.txt", "gunicorn" in req)
check("gevent in requirements.txt",   "gevent" in req)
check("flask in requirements.txt",    "flask" in req.lower())
check("anthropic in requirements.txt","anthropic" in req)

# ── App source ────────────────────────────────────────────────────────────────

app_src = (ROOT / "app.py").read_text()
check("MOCK_MODE is False",          "MOCK_MODE = False" in app_src,
      "MOCK_MODE = True would serve fake plans in production")
check("No hardcoded API key",        "sk-ant-" not in app_src,
      "API key must come from env var")
check("max_tokens <= 5000",
      any(f"max_tokens={n}" in app_src.replace(" ", "") for n in
          [str(x) for x in range(500, 5001)]),
      "max_tokens above 5000 will cause timeouts on Haiku")
check("Uses env var for API key",    'os.environ.get("ANTHROPIC_API_KEY")' in app_src or
                                      'os.environ.get("AI_INTEGRATIONS' in app_src)
check("ANALYTICS_KEY check present", "ANALYTICS_KEY" in app_src,
      "/analytics must be protected in production")

# ── Templates ─────────────────────────────────────────────────────────────────

for tmpl in ["index.html", "analytics.html"]:
    check(f"templates/{tmpl} exists", (ROOT / "templates" / tmpl).exists())

# ── Data directory ────────────────────────────────────────────────────────────

check("data/ directory exists", (ROOT / "data").exists())

# ── Live endpoint latency (optional — skipped if no API key set) ──────────────

prod_url = os.environ.get("PROD_URL", "").rstrip("/")
if prod_url:
    import urllib.request
    import urllib.error

    print(f"\nRunning live checks against {prod_url}...")

    # Homepage load time
    try:
        t0 = time.time()
        urllib.request.urlopen(prod_url + "/", timeout=10)
        ms = int((time.time() - t0) * 1000)
        check("Homepage loads in < 3s", ms < 3000, f"{ms}ms")
    except Exception as e:
        check("Homepage reachable", False, str(e))

    # Analytics key check (should 404 without key)
    try:
        code = 0
        try:
            urllib.request.urlopen(prod_url + "/analytics", timeout=5)
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        check("/analytics returns 404 without key in production", code == 404,
              f"got {code} — analytics must not be publicly accessible")
    except Exception as e:
        check("/analytics key protection", False, str(e))
else:
    print("\nSkipping live endpoint checks (set PROD_URL=https://yourapp.replit.app to enable)")

# ── Summary ───────────────────────────────────────────────────────────────────

print(f"\n{'─' * 50}")
if errors:
    print(f"FAILED — {len(errors)} issue(s) must be fixed before deploying:")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print("All checks passed — safe to deploy.")
    sys.exit(0)
