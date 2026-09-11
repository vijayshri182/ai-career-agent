"""Authentication adapter contract.

`AuthenticationAdapter` is the provider/site-neutral contract that future
site-specific adapters (e.g. a Workday or an ATS integration) must implement.
No site-specific adapters are implemented in this foundation.

Safety contract for implementers:
- Never bypass, solve, or defeat CAPTCHA / bot protection / MFA.
- Never read, store, or log passwords, OTPs, cookies, or tokens.
- When a challenge is detected, return it via `detect_challenge()` so the
  human-in-the-loop workflow pauses. Resume only after the human completes the
  site's own flow.
"""

from typing import Protocol, runtime_checkable

from backend.models.authentication import AuthState
from backend.services.challenge_detection import ChallengeClassification


@runtime_checkable
class AuthenticationAdapter(Protocol):
    """Contract every provider adapter implements."""

    provider_key: str

    def detect_authentication_state(self) -> AuthState:
        """Return the current authentication state for the linked session."""
        ...

    def authenticate_if_allowed(self, secret_reference: str) -> bool:
        """Attempt authentication only when the site explicitly permits
        automation. Returns True when a session is established."""
        ...

    def check_session(self) -> bool:
        """Return True when the session is still valid."""
        ...

    def detect_challenge(self) -> ChallengeClassification | None:
        """Return a classification when the site presented a challenge, else
        None. Implementations must never attempt to solve the challenge."""
        ...

    def request_human_action(self, reason: str) -> None:
        """Signal the workflow orchestrator that a human must act."""
        ...

    def resume_after_human_action(self) -> AuthState:
        """Re-check state after the human completed the site's flow."""
        ...

    def logout(self) -> None:
        """Close the session without touching stored secrets."""
        ...
