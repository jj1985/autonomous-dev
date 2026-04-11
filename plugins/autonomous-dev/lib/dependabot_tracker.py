"""Dependabot security issue tracker.

Queries the GitHub Dependabot API and creates deduplicated tracking issues
for vulnerabilities found in the target repository. Completely non-blocking:
any failure is logged with [dependabot-tracker] prefix and the pipeline continues.

Created for Issue #767.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# GHSA ID validation pattern: exactly GHSA-xxxx-xxxx-xxxx with lowercase alphanumeric
_GHSA_PATTERN = re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$")

# GitHub remote URL pattern: handles SSH and HTTPS
_GITHUB_REMOTE_PATTERN = re.compile(r"github\.com[:/]([^/]+)/([^/.]+)")

_LOG_PREFIX = "[dependabot-tracker]"


def parse_owner_repo(remote_url: str) -> Optional[Tuple[str, str]]:
    """Parse GitHub owner and repo from a git remote URL.

    Supports SSH (git@github.com:owner/repo.git) and HTTPS
    (https://github.com/owner/repo.git or without .git suffix).

    Args:
        remote_url: Git remote URL string.

    Returns:
        Tuple of (owner, repo) or None if not a GitHub remote.
    """
    match = _GITHUB_REMOTE_PATTERN.search(remote_url)
    if match:
        return match.group(1), match.group(2)
    return None


def _gh(args: List[str], *, timeout: int = 30) -> Optional[object]:
    """Run a gh CLI command and return parsed JSON output.

    Args:
        args: List of arguments to pass after 'gh'.
        timeout: Command timeout in seconds.

    Returns:
        Parsed JSON (dict or list) on success, None on any error.
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _validate_ghsa_id(ghsa_id: str) -> bool:
    """Validate a GHSA ID against the expected format.

    Args:
        ghsa_id: GHSA identifier to validate.

    Returns:
        True if valid GHSA-xxxx-xxxx-xxxx format with lowercase alphanumeric.
    """
    if not ghsa_id or not isinstance(ghsa_id, str):
        return False
    return bool(_GHSA_PATTERN.fullmatch(ghsa_id))


def get_open_alerts(owner: str, repo: str) -> List[Dict]:
    """Fetch open Dependabot alerts from GitHub API.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        List of alert dicts, empty list on any error.
    """
    try:
        result = _gh([
            "api",
            f"/repos/{owner}/{repo}/dependabot/alerts",
            "--jq", ".",
            "-f", "state=open",
        ])
        if isinstance(result, list):
            return result
        return []
    except Exception:
        return []


def issue_exists_for_ghsa(owner: str, repo: str, ghsa_id: str) -> bool:
    """Check if a GitHub issue already exists for a GHSA ID.

    Searches issue bodies for the HTML comment marker <!-- GHSA: {ghsa_id} -->.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        ghsa_id: GHSA identifier to search for.

    Returns:
        True if an issue with the marker exists, False otherwise or on error.
    """
    if not _validate_ghsa_id(ghsa_id):
        return False
    try:
        marker = f"<!-- GHSA: {ghsa_id} -->"
        result = _gh([
            "issue", "list",
            "-R", f"{owner}/{repo}",
            "--search", ghsa_id,
            "--state", "all",
            "--json", "body",
            "--limit", "100",
        ])
        if not isinstance(result, list):
            return False
        for issue in result:
            body = issue.get("body", "") or ""
            if marker in body:
                return True
        return False
    except Exception:
        return False


def create_individual_issue(owner: str, repo: str, alert: Dict) -> bool:
    """Create a GitHub issue for a critical or high severity alert.

    Title format: security({package}): {GHSA-ID} [{severity}]
    Body includes HTML comment marker for deduplication.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        alert: Dependabot alert dict from the API.

    Returns:
        True if issue was created successfully, False otherwise.
    """
    try:
        ghsa_id = alert.get("security_advisory", {}).get("ghsa_id", "")
        if not _validate_ghsa_id(ghsa_id):
            print(f"{_LOG_PREFIX} Invalid GHSA ID: skipping alert")
            return False

        severity = alert.get("security_advisory", {}).get("severity", "unknown")
        package_name = (
            alert.get("security_vulnerability", {})
            .get("package", {})
            .get("name", "unknown")
        )
        summary = alert.get("security_advisory", {}).get("summary", "No summary available")
        cve_id = alert.get("security_advisory", {}).get("cve_id", "N/A")
        html_url = alert.get("html_url", "")

        title = f"security({package_name}): {ghsa_id} [{severity}]"
        body = (
            f"<!-- GHSA: {ghsa_id} -->\n\n"
            f"## Dependabot Security Alert\n\n"
            f"**Package**: {package_name}\n"
            f"**Severity**: {severity}\n"
            f"**GHSA**: {ghsa_id}\n"
            f"**CVE**: {cve_id}\n\n"
            f"### Summary\n\n{summary}\n\n"
            f"**Alert URL**: {html_url}\n\n"
            f"---\n"
            f"*Auto-created by dependabot-tracker (Issue #767)*"
        )

        result = _gh([
            "issue", "create",
            "-R", f"{owner}/{repo}",
            "--title", title,
            "--body", body,
            "--label", "security",
            "--label", "dependabot",
        ])
        return result is not None
    except Exception as e:
        print(f"{_LOG_PREFIX} Error creating issue: {e}")
        return False


def _maybe_create_medium_batch(
    owner: str, repo: str, medium_alerts: List[Dict]
) -> bool:
    """Create a single batch issue for medium severity alerts grouped by ISO week.

    Uses marker <!-- GHSA-BATCH: {year}-W{week} --> for deduplication.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        medium_alerts: List of medium severity alert dicts.

    Returns:
        True if a batch issue was created, False if skipped or error.
    """
    if not medium_alerts:
        return False

    try:
        now = datetime.now(timezone.utc)
        iso_year, iso_week, _ = now.isocalendar()
        batch_marker = f"<!-- GHSA-BATCH: {iso_year}-W{iso_week:02d} -->"

        # Check if batch issue already exists for this week
        search_result = _gh([
            "issue", "list",
            "-R", f"{owner}/{repo}",
            "--search", f"GHSA-BATCH {iso_year}-W{iso_week:02d}",
            "--state", "all",
            "--json", "body",
            "--limit", "50",
        ])
        if isinstance(search_result, list):
            for issue in search_result:
                body = issue.get("body", "") or ""
                if batch_marker in body:
                    return False  # Already exists for this week

        # Build batch issue body
        alert_lines = []
        for alert in medium_alerts:
            ghsa_id = alert.get("security_advisory", {}).get("ghsa_id", "")
            if not _validate_ghsa_id(ghsa_id):
                continue
            pkg = (
                alert.get("security_vulnerability", {})
                .get("package", {})
                .get("name", "unknown")
            )
            summary = alert.get("security_advisory", {}).get("summary", "")
            alert_lines.append(f"- **{pkg}** ({ghsa_id}): {summary}")

        if not alert_lines:
            return False

        title = f"security(batch): Medium severity alerts [{iso_year}-W{iso_week:02d}]"
        body = (
            f"{batch_marker}\n\n"
            f"## Medium Severity Dependabot Alerts\n\n"
            f"**Week**: {iso_year}-W{iso_week:02d}\n"
            f"**Count**: {len(alert_lines)}\n\n"
            f"### Alerts\n\n"
            + "\n".join(alert_lines)
            + "\n\n---\n"
            f"*Auto-created by dependabot-tracker (Issue #767)*"
        )

        result = _gh([
            "issue", "create",
            "-R", f"{owner}/{repo}",
            "--title", title,
            "--body", body,
            "--label", "security",
            "--label", "dependabot",
        ])
        return result is not None
    except Exception as e:
        print(f"{_LOG_PREFIX} Error creating batch issue: {e}")
        return False


def run_dependabot_tracker(owner: str, repo: str) -> Dict[str, int]:
    """Non-blocking entry point for Dependabot security issue tracking.

    Fetches open alerts, categorizes by severity, and creates deduplicated
    tracking issues. Critical/high get individual issues, medium gets batched
    by ISO week, low is skipped entirely.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        Dict with keys 'created', 'skipped', 'errors' (all ints).
    """
    try:
        result: Dict[str, int] = {"created": 0, "skipped": 0, "errors": 0}

        alerts = get_open_alerts(owner, repo)
        if not alerts:
            return result

        medium_alerts: List[Dict] = []

        for alert in alerts:
            severity = (
                alert.get("security_advisory", {}).get("severity", "").lower()
            )
            ghsa_id = alert.get("security_advisory", {}).get("ghsa_id", "")

            if severity == "low":
                result["skipped"] += 1
                continue

            if severity == "medium":
                medium_alerts.append(alert)
                continue

            # Critical or high: individual issue
            if severity in ("critical", "high"):
                if not _validate_ghsa_id(ghsa_id):
                    result["errors"] += 1
                    continue

                try:
                    if issue_exists_for_ghsa(owner, repo, ghsa_id):
                        result["skipped"] += 1
                        continue
                    if create_individual_issue(owner, repo, alert):
                        result["created"] += 1
                    else:
                        result["errors"] += 1
                except Exception:
                    result["errors"] += 1
            else:
                # Unknown severity: skip
                result["skipped"] += 1

        # Process medium batch
        if medium_alerts:
            try:
                if _maybe_create_medium_batch(owner, repo, medium_alerts):
                    result["created"] += 1
                else:
                    result["skipped"] += len(medium_alerts)
            except Exception:
                result["errors"] += 1

        return result
    except Exception as e:
        print(f"{_LOG_PREFIX} Unexpected error: {e}")
        return {"created": 0, "skipped": 0, "errors": 1}
