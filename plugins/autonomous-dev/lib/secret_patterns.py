"""
Shared secret patterns module — single source of truth for credential detection.

Used by:
- hooks/security_scan.py (pre-commit scanning)
- lib/active_security_scanner.py (active security scanning)

Issue #710: Active security scanning.
"""

import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# SECRET_PATTERNS — credential detection regexes
# Each tuple: (regex_pattern, human_readable_description)
# ---------------------------------------------------------------------------

SECRET_PATTERNS: List[Tuple[str, str]] = [
    # API keys
    (r"sk-[a-zA-Z0-9]{20,}", "Anthropic API key"),
    (r"sk-proj-[a-zA-Z0-9]{20,}", "OpenAI API key"),
    (r"xoxb-[a-zA-Z0-9-]{40,}", "Slack bot token"),
    (r"ghp_[a-zA-Z0-9]{36,}", "GitHub personal access token"),
    (r"gho_[a-zA-Z0-9]{36,}", "GitHub OAuth token"),
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"(?i)aws_secret_access_key.*[=:].*[a-zA-Z0-9/+=]{40}", "AWS secret key"),
    # Generic patterns
    (r'(?i)(api[_-]?key|apikey).*[=:].*["\'][a-zA-Z0-9]{20,}["\']', "Generic API key"),
    (r'(?i)(secret|password|passwd|pwd).*[=:].*["\'][^"\']{8,}["\']', "Generic secret"),
    (r'(?i)token.*[=:].*["\'][a-zA-Z0-9]{20,}["\']', "Generic token"),
    # Database URLs with credentials
    (r"(?i)(mongodb|mysql|postgres)://[^:]+:[^@]+@", "Database URL with credentials"),
    # Private keys
    (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
]

# Compiled patterns for efficient reuse
COMPILED_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern), description) for pattern, description in SECRET_PATTERNS
]


# ---------------------------------------------------------------------------
# OWASP_CODE_PATTERNS — dangerous code patterns
# Each tuple: (regex_pattern, owasp_category, remediation_text)
# ---------------------------------------------------------------------------

OWASP_CODE_PATTERNS: List[Tuple[str, str, str]] = [
    # A03: Injection — shell=True command injection
    (
        r"subprocess\.\w+\(.*shell\s*=\s*True",
        "A03: Command Injection (shell=True)",
        "Use subprocess with shell=False and pass arguments as a list. "
        "Example: subprocess.run(['cmd', 'arg1'], shell=False)",
    ),
    # A03: Injection — eval/exec code injection
    (
        r"\beval\s*\(",
        "A03: Code Injection (eval)",
        "Replace eval() with ast.literal_eval() for data parsing, "
        "or use a safe expression evaluator. eval() executes arbitrary code.",
    ),
    (
        r"\bexec\s*\(",
        "A03: Code Injection (exec)",
        "Avoid exec() — it executes arbitrary code. Use safer alternatives "
        "like importlib for dynamic imports or a restricted execution sandbox.",
    ),
    # A03: Injection — SQL injection via string formatting
    (
        r"""(?:execute|cursor\.execute)\s*\(\s*(?:f['\"]|['\"].*%s|.*\.format\()""",
        "A03: SQL Injection (string formatting)",
        "Use parameterized queries instead of string formatting. "
        "Example: cursor.execute('SELECT * FROM t WHERE id = ?', (user_id,))",
    ),
    # A05: Security Misconfiguration — debug mode
    (
        r"(?i)\bdebug\s*=\s*True\b",
        "A05: Security Misconfiguration (debug=True)",
        "Set debug=False in production. Use environment variables to "
        "control debug mode: debug = os.getenv('DEBUG', 'false').lower() == 'true'",
    ),
    # A10: SSRF — URL construction from user input
    (
        r"""requests\.(?:get|post|put|delete|patch)\s*\(\s*(?:f['\"]|.*\+\s*|.*\.format\()""",
        "A10: SSRF (dynamic URL construction)",
        "Validate and allowlist URLs before making requests. "
        "Use urllib.parse to validate scheme and hostname against an allowlist.",
    ),
]

# Compiled OWASP patterns
COMPILED_OWASP_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(pattern), category, remediation)
    for pattern, category, remediation in OWASP_CODE_PATTERNS
]


# ---------------------------------------------------------------------------
# DEPENDENCY_ADVISORIES — known vulnerable version ranges
# ---------------------------------------------------------------------------

DEPENDENCY_ADVISORIES: dict = {
    "django": [
        {
            "affected_versions": "<3.2.25",
            "severity": "HIGH",
            "cve": "CVE-2024-27351",
            "description": "Potential regular expression DoS in django.utils.text.Truncator",
            "remediation": "Upgrade Django to >= 3.2.25, >= 4.2.11, or >= 5.0.3",
        },
    ],
    "flask": [
        {
            "affected_versions": "<2.3.2",
            "severity": "HIGH",
            "cve": "CVE-2023-30861",
            "description": "Session cookie set without Secure flag on redirects",
            "remediation": "Upgrade Flask to >= 2.3.2",
        },
    ],
    "requests": [
        {
            "affected_versions": "<2.31.0",
            "severity": "MEDIUM",
            "cve": "CVE-2023-32681",
            "description": "Unintended leak of Proxy-Authorization header",
            "remediation": "Upgrade requests to >= 2.31.0",
        },
    ],
    "urllib3": [
        {
            "affected_versions": "<2.0.7",
            "severity": "MEDIUM",
            "cve": "CVE-2023-45803",
            "description": "Request body not stripped after redirect",
            "remediation": "Upgrade urllib3 to >= 2.0.7 or >= 1.26.18",
        },
    ],
    "cryptography": [
        {
            "affected_versions": "<41.0.6",
            "severity": "HIGH",
            "cve": "CVE-2023-49083",
            "description": "NULL pointer dereference in PKCS12 parsing",
            "remediation": "Upgrade cryptography to >= 41.0.6",
        },
    ],
    "pillow": [
        {
            "affected_versions": "<10.2.0",
            "severity": "HIGH",
            "cve": "CVE-2023-50447",
            "description": "Arbitrary code execution via crafted image",
            "remediation": "Upgrade Pillow to >= 10.2.0",
        },
    ],
    "jinja2": [
        {
            "affected_versions": "<3.1.3",
            "severity": "MEDIUM",
            "cve": "CVE-2024-22195",
            "description": "Cross-site scripting via xmlattr filter",
            "remediation": "Upgrade Jinja2 to >= 3.1.3",
        },
    ],
    "pyyaml": [
        {
            "affected_versions": "<6.0.1",
            "severity": "HIGH",
            "cve": "CVE-2020-14343",
            "description": "Arbitrary code execution via yaml.load()",
            "remediation": "Upgrade PyYAML to >= 6.0.1 and use yaml.safe_load()",
        },
    ],
}
