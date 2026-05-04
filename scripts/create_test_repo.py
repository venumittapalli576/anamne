"""
Creates a realistic test git repository with meaningful commit history
so you can demo PROVENANCE without needing your own codebase.

Usage:
    python scripts/create_test_repo.py
    provenance index ./test-repo
    provenance ask "why was Redis added?"
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path("./test-repo")

COMMITS = [
    # (filename, content, commit_message)
    (
        "README.md",
        "# ShopAPI\nA simple e-commerce backend API.",
        "Initial commit: scaffold ShopAPI project",
    ),
    (
        "auth/jwt.py",
        "# JWT authentication handler\nimport jwt\n\ndef verify(token): ...",
        "Add JWT authentication\n\nUsers need to authenticate before accessing any endpoint. "
        "Chose JWT because it is stateless — no session store needed for the MVP.",
    ),
    (
        "db/models.py",
        "# SQLAlchemy models\nfrom sqlalchemy import Column, Integer, String",
        "Add SQLAlchemy ORM models\n\nWe picked SQLAlchemy over raw SQL so the team can switch "
        "databases without rewriting queries. Starting with SQLite for dev, PostgreSQL for prod.",
    ),
    (
        "api/products.py",
        "# Products endpoint\nfrom fastapi import APIRouter\nrouter = APIRouter()",
        "Add /products REST endpoint\n\nProduct catalog is read-heavy so we exposed it as REST. "
        "Considered GraphQL but REST is simpler and the mobile team already has axios wrappers.",
    ),
    (
        "cache/redis.py",
        "# Redis cache layer\nimport redis\nclient = redis.Redis(host='localhost')",
        "Add Redis caching for product listings\n\nLoad testing showed /products timing out at "
        "200 concurrent users because every request hit the DB. Added Redis with a 5-minute TTL. "
        "Cache invalidation on product update. Reduced p99 latency from 4200ms to 180ms.",
    ),
    (
        "auth/jwt.py",
        "# Switched to opaque tokens\n# JWT was vulnerable to XSS via localStorage",
        "Replace JWT with opaque tokens\n\nSecurity audit (ticket SEC-1234) found that JWTs "
        "stored in localStorage are vulnerable to XSS attacks. Switched to opaque tokens stored "
        "in httpOnly cookies. Requires a token store (Redis) but eliminates the XSS risk.",
    ),
    (
        "payments/stripe.py",
        "# Stripe payment integration\nimport stripe",
        "Integrate Stripe for payments\n\nEvaluated Stripe vs Braintree vs PayPal. Chose Stripe "
        "because: best developer docs, PCI-DSS compliance handled for us, and the team has prior "
        "experience. PayPal rejected — high dispute rates. Braintree rejected — worse SDK.",
    ),
    (
        "workers/email.py",
        "# Celery email worker\nfrom celery import Celery\napp = Celery()",
        "Add async email delivery via Celery\n\nSynchronous email sending was blocking the "
        "checkout response for 800-1200ms. Moved to Celery + Redis queue. Checkout now returns "
        "immediately. Emails deliver within 2 seconds in testing.",
    ),
    (
        "api/search.py",
        "# Full-text search endpoint\nfrom elasticsearch import Elasticsearch",
        "Add Elasticsearch for product search\n\nPostgreSQL LIKE queries on 50k products were "
        "unacceptably slow (3-8 seconds). Added Elasticsearch for full-text search with "
        "fuzzy matching. Considered Algolia but self-hosting saves $400/month at our scale.",
    ),
    (
        "monitoring/metrics.py",
        "# Prometheus metrics\nfrom prometheus_client import Counter",
        "Add Prometheus metrics and Grafana dashboard\n\nAfter the Redis outage last month we had "
        "no visibility into what was happening. Added Prometheus scraping + Grafana boards. "
        "On-call team can now see cache hit rates, DB connection pool, and API latency in real time.",
    ),
]


def run(cmd: str, cwd: Path = REPO) -> None:
    subprocess.run(cmd, shell=True, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    if REPO.exists():
        print(f"[FAIL] {REPO} already exists. Delete it first.")
        sys.exit(1)

    REPO.mkdir()
    run("git init", cwd=REPO)
    run('git config user.email "demo@provenance.ai"', cwd=REPO)
    run('git config user.name "Demo User"', cwd=REPO)

    for filename, content, message in COMMITS:
        file_path = REPO / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        run(f'git add "{filename}"', cwd=REPO)
        # Write message to a temp file to handle multi-line messages
        msg_file = REPO / ".git" / "COMMIT_MSG_TMP"
        msg_file.write_text(message, encoding="utf-8")
        run('git commit -F ".git/COMMIT_MSG_TMP"', cwd=REPO)
        msg_file.unlink()

    print(f"[OK] Created test repo at {REPO.resolve()}")
    print(f"  {len(COMMITS)} commits with meaningful architectural decisions\n")
    print("Now run:")
    print(f"  provenance index {REPO}")
    print('  provenance ask "why was Redis added?"')
    print('  provenance ask "why was JWT replaced?"')
    print('  provenance ask "why was Elasticsearch chosen over PostgreSQL search?"')


if __name__ == "__main__":
    main()
