"""Robots.txt compliance for job discovery.

Implements the RFC 9309 robot exclusion protocol at the level the discovery
pipeline needs: resolve the effective user agent, apply longest-prefix path
matching for allow/deny rules, and expose crawl-delay. No anti-bot bypass is
possible here by design — this module only enforces what the site permits.
"""

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

_ACTION_FIELDS = {"allow", "disallow", "crawl-delay"}


@dataclass
class _Rule:
    prefix: str
    allow: bool


@dataclass
class RobotsTxt:
    """Parsed robots.txt with an easy ``allows(path)`` answer."""

    user_agent: str
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None

    def allows(self, request_path: str) -> bool:
        """Whether the effective user agent may fetch ``request_path``.

        RFC 9309: the longest matching prefix wins; empty allow rules mean
        "allow all" (represented as a catch-all allow initialized first).
        """
        if not self.rules:
            return True
        best_match: _Rule | None = None
        for rule in self.rules:
            if request_path.startswith(rule.prefix) and (
                best_match is None or len(rule.prefix) >= len(best_match.prefix)
            ):
                best_match = rule
        return best_match.allow if best_match is not None else True


def parse_robots_txt(
    text: str, user_agent: str, default_crawl_delay: float | None = None
) -> RobotsTxt:
    """Parse robots.txt content into a policy for ``user_agent``."""
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()
        if field_name == "user-agent":
            if current is not None and any(k in _ACTION_FIELDS for k, _ in current):
                groups.append(current)
            current = []
            current.append((field_name, value))
        elif current is not None and field_name in _ACTION_FIELDS:
            current.append((field_name, value))
    if current is not None and any(k in _ACTION_FIELDS for k, _ in current):
        groups.append(current)

    effective = _select_group(groups, user_agent)
    rules: list[_Rule] = []
    crawl_delay: float | None = None
    for field_name, value in effective:
        if field_name == "crawl-delay":
            try:
                crawl_delay = float(value)
            except ValueError:
                continue
            continue
        prefix = _normalize_path(value)
        if field_name == "allow":
            rules.append(_Rule(prefix or "", True))
        else:  # disallow
            # RFC 9309: an empty Disallow value ("Disallow:") means no rule and
            # allows everything; "Disallow: /" blocks everything, which later
            # allow rules with longer prefixes can override.
            if prefix == "":
                continue
            rules.append(_Rule(prefix, False))
    # Default: no rules mean crawl everything.
    if not rules:
        rules = [_Rule("", True)]
    return RobotsTxt(user_agent=user_agent, rules=rules, crawl_delay=crawl_delay or default_crawl_delay)


def _select_group(groups: list[list[tuple[str, str]]], user_agent: str) -> list[tuple[str, str]]:
    ua = user_agent.lower()
    wildcard: list[tuple[str, str]] | None = None
    best: list[tuple[str, str]] | None = None
    for group in groups:
        agent_names = [value for key, value in group if key == "user-agent"]
        if not agent_names:
            continue
        for name in agent_names:
            lowered = name.lower().strip("*")
            if lowered == "":
                wildcard = group
            elif lowered in ua and (best is None or len(lowered) > _group_agent_len(best)):
                best = group
    return best or wildcard or []


def _group_agent_len(group: list[tuple[str, str]] | None) -> int:
    names = [value for key, value in group or [] if key == "user-agent"]
    return max((len(n.strip("*")) for n in names), default=0)


def _normalize_path(value: str) -> str:
    if value == "" or value == "*":
        return ""
    if not value.startswith("/"):
        return "/" + value
    return value


def robots_url_for(base_url: str) -> str:
    """Return the robots.txt URL for a source base URL."""
    parts = urlsplit(base_url)
    base = f"{parts.scheme}://{parts.netloc}"
    return urljoin(base, "/robots.txt")


def request_path_for(url: str) -> str:
    """Return the path+query portion used for robots prefix matching."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return path
