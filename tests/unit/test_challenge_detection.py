"""Unit tests for challenge signal classification."""

from backend.models.authentication import AuthState
from backend.models.challenge import ChallengeType
from backend.services.challenge_detection import (
    ChallengeSignals,
    challenge_type_for_state,
    classify_challenge,
)


class TestClassifyChallenge:
    def test_captcha_hint(self):
        c = classify_challenge(
            ChallengeSignals(
                http_status=200,
                page_title="Sign in",
                text_hints=["Please verify you are human", "recaptcha"],
            )
        )
        assert c is not None
        assert c.challenge_type == ChallengeType.CAPTCHA
        assert c.auth_state == AuthState.CAPTCHA_REQUIRED

    def test_mfa_hint(self):
        c = classify_challenge(
            ChallengeSignals(
                http_status=200,
                page_title="Two-factor authentication",
                text_hints=["Enter the code from your authenticator app"],
            )
        )
        assert c is not None
        assert c.challenge_type == ChallengeType.MFA
        assert c.auth_state == AuthState.MFA_REQUIRED

    def test_bot_protection(self):
        c = classify_challenge(
            ChallengeSignals(
                http_status=200,
                page_title="Access denied",
                text_hints=["We have detected automated access to this site"],
            )
        )
        assert c is not None
        assert c.challenge_type == ChallengeType.BOT_PROTECTION
        assert c.auth_state == AuthState.ACCESS_BLOCKED

    def test_http_429(self):
        c = classify_challenge(ChallengeSignals(http_status=429))
        assert c is not None
        assert c.challenge_type == ChallengeType.RATE_LIMIT
        assert c.auth_state == AuthState.RATE_LIMITED
        assert c.human_required is False

    def test_http_401(self):
        c = classify_challenge(ChallengeSignals(http_status=401))
        assert c is not None
        assert c.challenge_type == ChallengeType.LOGIN_REQUIRED
        assert c.auth_state == AuthState.AUTHENTICATION_REQUIRED

    def test_http_403(self):
        c = classify_challenge(ChallengeSignals(http_status=403))
        assert c is not None
        assert c.challenge_type == ChallengeType.ACCESS_DENIED
        assert c.auth_state == AuthState.ACCESS_BLOCKED

    def test_session_expired(self):
        c = classify_challenge(
            ChallengeSignals(http_status=200, text_hints=["Your session has expired"])
        )
        assert c is not None
        assert c.challenge_type == ChallengeType.SESSION_EXPIRED
        assert c.auth_state == AuthState.SESSION_EXPIRED

    def test_login_prompt(self):
        c = classify_challenge(
            ChallengeSignals(http_status=200, text_hints=["Email address and password"])
        )
        assert c is not None
        assert c.challenge_type == ChallengeType.LOGIN_REQUIRED

    def test_no_match_returns_none(self):
        c = classify_challenge(
            ChallengeSignals(http_status=200, page_title="Dashboard", text_hints=["Welcome back"])
        )
        assert c is None

    def test_blocked_access_matches_critical(self):
        c = classify_challenge(
            ChallengeSignals(http_status=200, text_hints=["We have stopped your access"])
        )
        assert c is not None
        assert c.severity == "critical"


class TestChallengeTypeForState:
    def test_maps_all_escalation_states(self):
        assert challenge_type_for_state(AuthState.CAPTCHA_REQUIRED) == ChallengeType.CAPTCHA
        assert challenge_type_for_state(AuthState.MFA_REQUIRED) == ChallengeType.MFA
        assert (
            challenge_type_for_state(AuthState.ACCESS_BLOCKED) == ChallengeType.ACCESS_DENIED
        )
        assert challenge_type_for_state(AuthState.RATE_LIMITED) == ChallengeType.RATE_LIMIT
        assert (
            challenge_type_for_state(AuthState.SESSION_EXPIRED)
            == ChallengeType.SESSION_EXPIRED
        )
        assert (
            challenge_type_for_state(AuthState.AUTHENTICATION_REQUIRED)
            == ChallengeType.LOGIN_REQUIRED
        )

    def test_returns_none_for_non_challenge_state(self):
        assert challenge_type_for_state(AuthState.AUTHENTICATED) is None
        assert challenge_type_for_state(AuthState.NOT_REQUIRED) is None
        assert challenge_type_for_state(AuthState.NOT_CONFIGURED) is None
