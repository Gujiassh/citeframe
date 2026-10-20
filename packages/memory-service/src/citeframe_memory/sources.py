"""Exact manual instruction resolution, without shared model access."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from citeframe_contracts.memory import AccessContext, AccessPort, InstructionSourceView, SourceUnavailable
from citeframe_persistence.models.memory import MemoryInstruction, MemorySource
from .access import require_private_management


def resolve_instruction(session: Session, access: AccessPort, context: AccessContext,
                        source_id: str) -> InstructionSourceView:
    require_private_management(context, context.actor_user_id)
    access.authorize(context, owner_user_id=context.actor_user_id)
    source = session.scalar(select(MemorySource).where(
        MemorySource.id == source_id, MemorySource.workspace_id == context.workspace_id,
        MemorySource.owner_user_id == context.actor_user_id).with_for_update())
    if source is None or source.state != "current":
        raise SourceUnavailable("source_unavailable")
    instruction = session.get(MemoryInstruction, source.instruction_id)
    if (instruction is None or instruction.erased_at is not None or not instruction.content
            or instruction.content_sha256 != source.content_sha256):
        raise SourceUnavailable("source_unavailable")
    return InstructionSourceView(source.id, instruction.id, instruction.actor_user_id,
                                 instruction.content, instruction.content_sha256, instruction.created_at)
