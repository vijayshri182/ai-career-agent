"""Unit tests for AuthStateMachine and WorkflowStateMachine."""

import pytest

from backend.core.exceptions import ValidationError
from backend.models.authentication import AuthenticationMethod, AuthState
from backend.models.workflow_run import WorkflowStatus
from backend.services.authentication_state import (
    HUMAN_ESCALATION_STATES,
    WORKFLOW_PAUSING_STATES,
    AuthStateMachine,
)
from backend.services.human_in_loop import WorkflowStateMachine


class TestAuthStateMachine:
    def test_initial_state_none(self):
        assert AuthStateMachine.initial_state(AuthenticationMethod.NONE) == AuthState.NOT_REQUIRED

    def test_initial_state_session(self):
        assert AuthStateMachine.initial_state(AuthenticationMethod.SESSION) == AuthState.NOT_CONFIGURED

    def test_initial_state_oauth(self):
        assert AuthStateMachine.initial_state(AuthenticationMethod.OAUTH) == AuthState.NOT_CONFIGURED

    def test_initial_state_password(self):
        assert AuthStateMachine.initial_state(AuthenticationMethod.PASSWORD) == AuthState.NOT_CONFIGURED

    def test_initial_state_api_key(self):
        assert AuthStateMachine.initial_state(AuthenticationMethod.API_KEY) == AuthState.NOT_CONFIGURED

    def test_valid_transition(self):
        result = AuthStateMachine.transition(
            AuthState.NOT_CONFIGURED, AuthState.AUTHENTICATED
        )
        assert result == AuthState.AUTHENTICATED

    def test_invalid_transition_raises(self):
        with pytest.raises(ValidationError, match="Illegal auth state transition"):
            AuthStateMachine.transition(
                AuthState.MFA_REQUIRED, AuthState.NOT_CONFIGURED
            )

    def test_can_transition_true(self):
        assert AuthStateMachine.can_transition(
            AuthState.NOT_CONFIGURED, AuthState.AUTHENTICATED
        )

    def test_can_transition_false(self):
        assert not AuthStateMachine.can_transition(
            AuthState.MFA_REQUIRED, AuthState.NOT_CONFIGURED
        )

    def test_escalation_states(self):
        assert {
            AuthState.MFA_REQUIRED,
            AuthState.CAPTCHA_REQUIRED,
            AuthState.ACCESS_BLOCKED,
            AuthState.HUMAN_ACTION_REQUIRED,
        } == HUMAN_ESCALATION_STATES

    def test_is_escalation(self):
        assert AuthStateMachine.is_escalation(AuthState.CAPTCHA_REQUIRED)
        assert not AuthStateMachine.is_escalation(AuthState.AUTHENTICATED)

    def test_pausing_states_superset_of_escalation(self):
        assert HUMAN_ESCALATION_STATES.issubset(WORKFLOW_PAUSING_STATES)

    def test_pauses_workflow(self):
        assert AuthStateMachine.pauses_workflow(AuthState.SESSION_EXPIRED)
        assert AuthStateMachine.pauses_workflow(AuthState.CAPTCHA_REQUIRED)
        assert not AuthStateMachine.pauses_workflow(AuthState.AUTHENTICATED)

    def test_authenticated_to_session_expired(self):
        result = AuthStateMachine.transition(
            AuthState.AUTHENTICATED, AuthState.SESSION_EXPIRED
        )
        assert result == AuthState.SESSION_EXPIRED

    def test_captcha_required_to_authenticated(self):
        result = AuthStateMachine.transition(
            AuthState.CAPTCHA_REQUIRED, AuthState.AUTHENTICATED
        )
        assert result == AuthState.AUTHENTICATED

    def test_access_blocked_to_human_action_required(self):
        result = AuthStateMachine.transition(
            AuthState.ACCESS_BLOCKED, AuthState.HUMAN_ACTION_REQUIRED
        )
        assert result == AuthState.HUMAN_ACTION_REQUIRED

    def test_access_blocked_direct_to_authenticated_rejected(self):
        with pytest.raises(ValidationError):
            AuthStateMachine.transition(AuthState.ACCESS_BLOCKED, AuthState.AUTHENTICATED)

    def test_error_can_go_to_authenticated(self):
        result = AuthStateMachine.transition(AuthState.ERROR, AuthState.AUTHENTICATED)
        assert result == AuthState.AUTHENTICATED

    def test_error_can_go_to_human_action(self):
        result = AuthStateMachine.transition(AuthState.ERROR, AuthState.HUMAN_ACTION_REQUIRED)
        assert result == AuthState.HUMAN_ACTION_REQUIRED


class TestWorkflowStateMachine:
    def test_terminal_states(self):
        assert {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TIMED_OUT,
            WorkflowStatus.FAILED,
        } == WorkflowStateMachine.TERMINAL_STATES

    def test_is_terminal(self):
        assert WorkflowStateMachine.is_terminal(WorkflowStatus.COMPLETED)
        assert not WorkflowStateMachine.is_terminal(WorkflowStatus.RUNNING)

    def test_running_to_paused(self):
        result = WorkflowStateMachine.transition(
            WorkflowStatus.RUNNING, WorkflowStatus.PAUSED_HUMAN_ACTION
        )
        assert result == WorkflowStatus.PAUSED_HUMAN_ACTION

    def test_paused_to_resumed(self):
        result = WorkflowStateMachine.transition(
            WorkflowStatus.PAUSED_HUMAN_ACTION, WorkflowStatus.RESUMED
        )
        assert result == WorkflowStatus.RESUMED

    def test_running_to_completed(self):
        result = WorkflowStateMachine.transition(
            WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED
        )
        assert result == WorkflowStatus.COMPLETED

    def test_paused_to_running(self):
        result = WorkflowStateMachine.transition(
            WorkflowStatus.PAUSED_HUMAN_ACTION, WorkflowStatus.RUNNING
        )
        assert result == WorkflowStatus.RUNNING

    def test_terminal_no_transitions(self):
        for terminal in WorkflowStateMachine.TERMINAL_STATES:
            assert WorkflowStateMachine.TRANSITIONS[terminal] == frozenset()

    def test_invalid_terminal_transition(self):
        with pytest.raises(ValidationError, match="Illegal workflow state transition"):
            WorkflowStateMachine.transition(
                WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING
            )

    def test_resumed_can_only_go_to_terminal(self):
        for target in {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED_HUMAN_ACTION, WorkflowStatus.RESUMED}:
            with pytest.raises(ValidationError):
                WorkflowStateMachine.transition(WorkflowStatus.RESUMED, target)
