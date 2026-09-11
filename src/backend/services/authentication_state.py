"""Authentication state machine (provider/site neutral).

Documents the allowed transitions between AuthState values. Serving as the
single source of truth, this module makes it impossible for callers to move a
provider into an illegal state. States that require human verification
(CAPTCHA, MFA, access blocked, general human action) are said to escalate and
can only be left through explicit, authorized paths (human resolved → AUTHENTICATED,
session expired again, or a declared error).
"""

from backend.core.exceptions import ValidationError
from backend.models.authentication import AuthenticationMethod, AuthState

#: States that require a human in the loop to make progress safely.
HUMAN_ESCALATION_STATES: frozenset[AuthState] = frozenset(
    {
        AuthState.MFA_REQUIRED,
        AuthState.CAPTCHA_REQUIRED,
        AuthState.ACCESS_BLOCKED,
        AuthState.HUMAN_ACTION_REQUIRED,
    }
)

#: States that pause the linked workflow until a human resolves the challenge.
WORKFLOW_PAUSING_STATES: frozenset[AuthState] = HUMAN_ESCALATION_STATES | frozenset(
    {AuthState.SESSION_EXPIRED, AuthState.AUTHENTICATION_REQUIRED, AuthState.RATE_LIMITED}
)

AUTH_STATE_TRANSITIONS: dict[AuthState, frozenset[AuthState]] = {
    AuthState.NOT_CONFIGURED: frozenset(
        {
            AuthState.NOT_REQUIRED,
            AuthState.AUTHENTICATED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.RATE_LIMITED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.NOT_REQUIRED: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.SESSION_EXPIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.RATE_LIMITED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.AUTHENTICATED: frozenset(
        {
            AuthState.NOT_REQUIRED,
            AuthState.SESSION_EXPIRED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.RATE_LIMITED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.SESSION_EXPIRED: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.RATE_LIMITED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.AUTHENTICATION_REQUIRED: frozenset(
        {
            AuthState.NOT_REQUIRED,
            AuthState.AUTHENTICATED,
            AuthState.SESSION_EXPIRED,
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.RATE_LIMITED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    # Human-verification states may not silently disappear: only an explicit
    # human resolution (AUTHENTICATED), a declared session problem, a fallback
    # to a general human-action request, a fresh error, or re-requested auth
    # may leave them.
    AuthState.MFA_REQUIRED: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.SESSION_EXPIRED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.CAPTCHA_REQUIRED: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.SESSION_EXPIRED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.ACCESS_BLOCKED: frozenset(
        {AuthState.HUMAN_ACTION_REQUIRED, AuthState.ERROR}
    ),
    AuthState.RATE_LIMITED: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.SESSION_EXPIRED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.HUMAN_ACTION_REQUIRED: frozenset(
        {
            AuthState.NOT_REQUIRED,
            AuthState.AUTHENTICATED,
            AuthState.SESSION_EXPIRED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.ERROR,
        }
    ),
    AuthState.ERROR: frozenset(
        {
            AuthState.AUTHENTICATED,
            AuthState.AUTHENTICATION_REQUIRED,
            AuthState.SESSION_EXPIRED,
            AuthState.HUMAN_ACTION_REQUIRED,
            AuthState.ERROR,
        }
    ),
}


class AuthStateMachine:
    """Pure transition rules; no I/O."""

    @staticmethod
    def can_transition(current: AuthState, target: AuthState) -> bool:
        return target in AUTH_STATE_TRANSITIONS.get(current, frozenset())

    @staticmethod
    def transition(current: AuthState, target: AuthState) -> AuthState:
        if not AuthStateMachine.can_transition(current, target):
            raise ValidationError(
                f"Illegal auth state transition: {current.value} -> {target.value}"
            )
        return target

    @staticmethod
    def initial_state(method: AuthenticationMethod) -> AuthState:
        if method == AuthenticationMethod.NONE:
            return AuthState.NOT_REQUIRED
        return AuthState.NOT_CONFIGURED

    @staticmethod
    def is_escalation(state: AuthState) -> bool:
        return state in HUMAN_ESCALATION_STATES

    @staticmethod
    def pauses_workflow(state: AuthState) -> bool:
        return state in WORKFLOW_PAUSING_STATES
