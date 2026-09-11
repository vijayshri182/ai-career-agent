"""Unit tests for robots.txt parsing (RFC 9309 subset)."""

from backend.services.robots import (
    parse_robots_txt,
    request_path_for,
    robots_url_for,
)


def test_empty_robots_allows_everything() -> None:
    robots = parse_robots_txt("", "career-agent-bot")
    assert robots.allows("/jobs") is True


def test_global_disallow_blocks() -> None:
    robots = parse_robots_txt("User-agent: *\nDisallow: /private", "career-agent-bot")
    assert robots.allows("/private/data") is False
    assert robots.allows("/jobs") is True


def test_longest_prefix_wins() -> None:
    text = "\n".join(
        [
            "User-agent: *",
            "Disallow: /",
            "Allow: /jobs",
            "Allow: /jobs/details",
        ]
    )
    robots = parse_robots_txt(text, "career-agent-bot")
    assert robots.allows("/") is False
    assert robots.allows("/about") is False
    assert robots.allows("/jobs") is True
    assert robots.allows("/jobs/details/123") is True
    assert robots.allows("/jobs/other") is True


def test_user_agent_group_selection_matches_substring() -> None:
    text = "\n".join(
        [
            "User-agent: Mozzarella",
            "Disallow: /restricted",
            "User-agent: Career-Agent-Spider",
            "Disallow: /",
        ]
    )
    robots = parse_robots_txt(text, "career-agent-spider/1.0")
    assert robots.allows("/anything") is False


def test_wildcard_group_fallback() -> None:
    text = "User-agent: *\nDisallow: /crawl-me"
    robots = parse_robots_txt(text, "some-other-bot")
    assert robots.allows("/crawl-me/x") is False
    assert robots.allows("/open") is True


def test_crawl_delay_parsed() -> None:
    robots = parse_robots_txt("User-agent: *\nCrawl-delay: 5", "any-bot")
    assert robots.crawl_delay == 5.0


def test_empty_disallow_means_allowed() -> None:
    robots = parse_robots_txt("User-agent: *\nDisallow:\nUser-agent: *\nAllow: /", "any-bot")
    assert robots.allows("/anything") is True


def test_robots_url_for() -> None:
    assert robots_url_for("https://example.com/jobs") == "https://example.com/robots.txt"


def test_request_path_for() -> None:
    assert request_path_for("https://example.com/jobs?q=eng") == "/jobs?q=eng"
