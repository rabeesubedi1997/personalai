import pytest

from app.models.request import Request, RequestStatus
from app.services.request_engine import InvalidTransitionError, RequestEngine


def _new_request() -> Request:
    return Request(
        tenant_id=None,  # not persisted in these unit tests
        request_type="test_type",
        status=RequestStatus.RECEIVED,
        status_history=[],
    )


def test_valid_forward_transition_succeeds():
    req = _new_request()
    RequestEngine.transition(req, RequestStatus.UNDERSTANDING)
    assert req.status == RequestStatus.UNDERSTANDING
    assert len(req.status_history) == 1
    assert req.status_history[0]["from"] == "received"
    assert req.status_history[0]["to"] == "understanding"


def test_invalid_skip_ahead_transition_rejected():
    req = _new_request()
    with pytest.raises(InvalidTransitionError):
        RequestEngine.transition(req, RequestStatus.COMPLETED)
    # Rejected transition must not mutate state.
    assert req.status == RequestStatus.RECEIVED
    assert req.status_history == []


def test_full_happy_path_lifecycle():
    req = _new_request()
    path = [
        RequestStatus.UNDERSTANDING,
        RequestStatus.VALIDATING,
        RequestStatus.SEARCHING,
        RequestStatus.MATCHING,
        RequestStatus.WAITING_FOR_CONFIRMATION,
        RequestStatus.EXECUTING,
        RequestStatus.VERIFYING,
        RequestStatus.COMPLETED,
    ]
    for step in path:
        RequestEngine.transition(req, step)
    assert req.status == RequestStatus.COMPLETED
    assert len(req.status_history) == len(path)


def test_can_always_cancel_from_non_terminal_state():
    req = _new_request()
    RequestEngine.transition(req, RequestStatus.UNDERSTANDING)
    RequestEngine.transition(req, RequestStatus.CANCELLED)
    assert req.status == RequestStatus.CANCELLED


def test_no_transitions_allowed_out_of_terminal_state():
    req = _new_request()
    RequestEngine.transition(req, RequestStatus.CANCELLED)
    assert RequestEngine.allowed_next_statuses(req.status) == set()
    with pytest.raises(InvalidTransitionError):
        RequestEngine.transition(req, RequestStatus.UNDERSTANDING)


def test_can_loop_back_for_more_information():
    req = _new_request()
    RequestEngine.transition(req, RequestStatus.UNDERSTANDING)
    RequestEngine.transition(req, RequestStatus.NEEDS_INFORMATION)
    RequestEngine.transition(req, RequestStatus.UNDERSTANDING)
    assert req.status == RequestStatus.UNDERSTANDING
    assert len(req.status_history) == 3
