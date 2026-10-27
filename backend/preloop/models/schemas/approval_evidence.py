"""Typed, unsigned approval evidence; distinct from RDT proof formats."""

from typing import Literal
from typing_extensions import TypedDict


class AuthenticationEvidence(TypedDict, total=False):
    type: Literal["api_key_credential", "authenticated_user_session"]
    credential_id: str


class AgentEvidence(TypedDict, total=False):
    id: str | None
    identity_status: Literal["not_established", "configured_association_unverified"]


class RequesterEvidence(TypedDict, total=False):
    account_id: str
    authenticated_user_id: str
    display_name: str
    display_name_source: Literal["authenticated_user_profile"]
    authentication: AuthenticationEvidence
    agent: AgentEvidence


class DelegationEvidence(TypedDict, total=False):
    status: Literal["not_recorded"]


class PurposeEvidence(TypedDict, total=False):
    status: Literal["supplied", "not_supplied"]
    source: Literal["caller_supplied_reasoning"] | None
    text: str | None
    verified: Literal[False]


class RuleEvidence(TypedDict, total=False):
    id: str | None
    action: str
    condition: str | None
    condition_type: str | None
    order: int | None
    content_digest: str
    digest_format: Literal["sha256:python-json-sortkeys-utf8-v1"]


class EvaluationContext(TypedDict, total=False):
    tool_name: str
    arguments_source: Literal["approval_request.tool_args"]
    completeness: Literal["minimal"]


class PolicyEvidence(TypedDict, total=False):
    evaluation_source: str
    evaluation_outcome: Literal["matched", "error_fallback"]
    matched_rule: RuleEvidence | None
    evaluated_rule: RuleEvidence | None
    approval_workflow_id: str | None
    scope: str | None
    action: str
    condition: str | None
    evaluated_at: str
    context: EvaluationContext


class WorkflowEvidence(TypedDict, total=False):
    id: str
    approval_type: str | None
    step_up_protocol: str | None
    timeout_seconds: int | None
    effective_step_up_required: bool


class AssessmentEvidence(TypedDict, total=False):
    source: Literal["intent_verifier"]
    model_used: str | None
    advisory: Literal[True]


class ServerRecordedContext(TypedDict, total=False):
    schema_version: Literal[1]
    record_type: Literal["server_recorded_context"]
    cryptographically_bound: Literal[False]
    requester: RequesterEvidence
    delegation: DelegationEvidence
    purpose: PurposeEvidence
    policy: PolicyEvidence
    workflow: WorkflowEvidence
    advisory_assessment: AssessmentEvidence
    expires_at: str | None
