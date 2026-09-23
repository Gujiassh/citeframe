"""Retain two real API-generated runs for an isolated visible UI walkthrough."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from issue25_service_support import Deployment, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    d = Deployment(args.directory, os.environ["CITEFRAME_TEST_POSTGRES_URL"])
    d.migrate()
    d.start_api()
    d.seed()
    runs = {}
    for mode in ("resolved", "unresolved"):
        d.create("Issue 25 visible " + mode)
        d.work(mode)
        value = d.request("GET", d.path).json()["run"]
        assert (
            value["status"] == "completed"
            and value["conflictInvestigation"]["status"] == mode
        )
        runs[mode] = {"id": d.run, "apiPath": d.path, "pageData": value}
    result = {
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "api": d.api,
        "apiPid": d.server.pid,
        "database": d.database,
        "workspaceId": d.workspace,
        "userId": d.user,
        "email": "issue25@example.test",
        "runs": runs,
    }
    d.capture("walkthrough", result)
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
    # Retain this lane's API and database until the UI owner finishes.
    d.engine.dispose()
    d.admin.dispose()


if __name__ == "__main__":
    main()
