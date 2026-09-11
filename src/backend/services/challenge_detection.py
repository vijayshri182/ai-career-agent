"""Provider-neutral challenge detection.

Converts raw signals (HTTP status, page title, urls, captcha/mfa keywords) into
a structured classification. Rule-based and modular: adding a new detection rule
is a matter of appending to the rules list. It never inspects cookies, tokens,
passwords, or OTP values — those are off-limits by design.

The classifier is deliberately conservative: when no rule matches it reports
UNKNOWN_HUMAN_VERIFICATION for anything that *looks* like an interactive gate,
otherwise None.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from backend.models.authentication import AuthState
from backend.models.challenge import ChallengeType


@dataclass(frozen=True)
class ChallengeSignals:
    """Safe, non-secret signals observed while interacting with a site."""

    http_status: int | None = None
    page_title: str | None = None
    url: str | None = None
    text_hints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChallengeClassification:
    challenge_type: ChallengeType
    auth_state: AuthState
    matched_rule: str
    human_required: bool
    severity: str
    reason: str | None = None


_MFA_HINTS = (
    "two-factor",
    "two factor",
    "2fa",
    "two-step",
    "one-time code",
    "one time code",
    "verification code",
    "authentication app",
    "authenticator",
    "security code",
    "enter the code",
)
_CAPTCHA_HINTS = ("captcha", "recaptcha", "hcaptcha", "g-recaptcha", "verify you are human", "i'm not a robot")
_BOT_HINTS = ("bot protection", "automated access", "access denied robot", "blocked because of bot")
_LOGIN_HINTS = ("sign in", "sign-in", "log in", "login", "password", "email address and password")
_SESSION_HINTS = ("session expired", "your session has expired", "session timeout", "please sign in again")
_RATE_HINT = ("rate limit", "too many requests", "please slow down", "retry later")
_ACCESS_DENIED_HINTS = ("access denied", "403", "forbidden", "not authorized", "you do not have access")
_BLOCK_HINTS = ("access blocked", "blocked", "we have stopped your access", "account restricted")


class DetectionRule:
    def __init__(
        self,
        name: str,
        match: Callable[[ChallengeSignals], bool],
        challenges: list[ChallengeType],
        auth_state: AuthState,
        human_required: bool = True,
        severity: str = "medium",
        reason: str | None = None,
    ) -> None:
        self.name = name
        self._match = match
        self.challenges = challenges
        self.auth_state = auth_state
        self.human_required = human_required
        self.severity = severity
        self.reason = reason

    def matches(self, signals: ChallengeSignals) -> bool:
        return self._match(signals)

    def classify(self) -> ChallengeClassification:
        return ChallengeClassification(
            challenge_type=self.challenges[0],
            auth_state=self.auth_state,
            matched_rule=self.name,
            human_required=self.human_required,
            severity=self.severity,
            reason=self.reason,
        )


def _status(status: int) -> Callable[[ChallengeSignals], bool]:
    def matcher(signals: ChallengeSignals) -> bool:
        return signals.http_status == status

    return matcher


def _any_hints(hints: tuple[str, ...]) -> Callable[[ChallengeSignals], bool]:
    def matcher(signals: ChallengeSignals) -> bool:
        haystack = " ".join([x.lower() for x in signals.text_hints or []])
        if signals.page_title:
            haystack += " " + signals.page_title.lower()
        return any(h in haystack for h in hints)

    return matcher


DETECTION_RULES: list[DetectionRule] = [
    DetectionRule(
        "captcha-present",
        _any_hints(_CAPTCHA_HINTS),
        [ChallengeType.CAPTCHA],
        AuthState.CAPTCHA_REQUIRED,
        severity="high",
        reason="Site presented a CAPTCHA/human-verification widget.",
    ),
    DetectionRule(
        "mfa-requested",
        _any_hints(_MFA_HINTS),
        [ChallengeType.MFA],
        AuthState.MFA_REQUIRED,
        severity="high",
        reason="Site requested a one-time/second-factor authentication step.",
    ),
    DetectionRule(
        "bot-protection",
        _any_hints(_BOT_HINTS),
        [ChallengeType.BOT_PROTECTION],
        AuthState.ACCESS_BLOCKED,
        severity="critical",
        reason="Site flagged automated access; do not attempt to bypass.",
    ),
    DetectionRule(
        "http-429",
        _status(429),
        [ChallengeType.RATE_LIMIT],
        AuthState.RATE_LIMITED,
        human_required=False,
        severity="low",
        reason="HTTP 429 rate limited.",
    ),
    DetectionRule(
        "rate-limit-hint",
        _any_hints(_RATE_HINT),
        [ChallengeType.RATE_LIMIT],
        AuthState.RATE_LIMITED,
        human_required=False,
        severity="low",
        reason="Rate-limit language detected.",
    ),
    DetectionRule(
        "session-expired",
        _any_hints(_SESSION_HINTS),
        [ChallengeType.SESSION_EXPIRED],
        AuthState.SESSION_EXPIRED,
        severity="medium",
        reason="Session expired language detected.",
    ),
    DetectionRule(
        "http-401",
        _status(401),
        [ChallengeType.LOGIN_REQUIRED],
        AuthState.AUTHENTICATION_REQUIRED,
        reason="HTTP 401 unauthorized.",
    ),
    DetectionRule(
        "login-required",
        _any_hints(_LOGIN_HINTS),
        [ChallengeType.LOGIN_REQUIRED],
        AuthState.AUTHENTICATION_REQUIRED,
        reason="Login prompt detected.",
    ),
    DetectionRule(
        "http-403",
        _status(403),
        [ChallengeType.ACCESS_DENIED],
        AuthState.ACCESS_BLOCKED,
        severity="high",
        reason="HTTP 403 forbidden.",
    ),
    DetectionRule(
        "access-denied",
        _any_hints(_ACCESS_DENIED_HINTS),
        [ChallengeType.ACCESS_DENIED],
        AuthState.ACCESS_BLOCKED,
        severity="high",
        reason="Access denied language detected.",
    ),
    DetectionRule(
        "access-blocked",
        _any_hints(_BLOCK_HINTS),
        [ChallengeType.BOT_PROTECTION],
        AuthState.ACCESS_BLOCKED,
        severity="critical",
        reason="Site indicated blocked access.",
    ),
]


def classify_challenge(signals: ChallengeSignals) -> ChallengeClassification | None:
    """Classify site signals into a challenge classification, if any."""
    for rule in DETECTION_RULES:
        if rule.matches(signals):
            return rule.classify()
    return None


_CHALLENGE_TYPE_FOR_STATE: dict[AuthState, ChallengeType] = {
    AuthState.CAPTCHA_REQUIRED: ChallengeType.CAPTCHA,
    AuthState.MFA_REQUIRED: ChallengeType.MFA,
    AuthState.ACCESS_BLOCKED: ChallengeType.ACCESS_DENIED,
    AuthState.RATE_LIMITED: ChallengeType.RATE_LIMIT,
    AuthState.SESSION_EXPIRED: ChallengeType.SESSION_EXPIRED,
    AuthState.AUTHENTICATION_REQUIRED: ChallengeType.LOGIN_REQUIRED,
    AuthState.HUMAN_ACTION_REQUIRED: ChallengeType.UNKNOWN_HUMAN_VERIFICATION,
}


def challenge_type_for_state(state: AuthState) -> ChallengeType | None:
    """Map an auth state to the challenge type that should be recorded."""
    return _CHALLENGE_TYPE_FOR_STATE.get(state)
