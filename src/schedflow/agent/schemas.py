"""Server authoritative chat block contract. No executable markup or UI commands."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantText(StrictModel):
    type: Literal["assistant_text"]
    text: str


class WorkflowResults(StrictModel):
    type: Literal["workflow_results"]
    jobs: list[dict]


class Option(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=200)


class Clarification(StrictModel):
    type: Literal["clarification"]
    text: str
    options: list[Option] = Field(min_length=1, max_length=5)


class ProposalBlock(StrictModel):
    type: Literal["proposal"]
    proposal_id: str
    version: int = Field(ge=1)


class OperationReceipt(StrictModel):
    type: Literal["operation_receipt"]
    operation_id: str


class ExecutionBlock(StrictModel):
    type: Literal["execution"]
    operation_id: str


class ErrorBlock(StrictModel):
    type: Literal["error"]
    message: str


AgentBlock = Annotated[
    AssistantText
    | WorkflowResults
    | Clarification
    | ProposalBlock
    | OperationReceipt
    | ExecutionBlock
    | ErrorBlock,
    Field(discriminator="type"),
]


class AgentMessage(StrictModel):
    message_id: str
    turn_id: str | None = None
    role: Literal["user", "assistant"]
    status: Literal["completed", "streaming", "failed", "cancelled", "interrupted"]
    blocks: list[AgentBlock]
