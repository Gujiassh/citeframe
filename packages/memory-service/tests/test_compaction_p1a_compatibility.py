"""Unchanged P1a behavior oracles executed on the complete Issue43 successor schema."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from citeframe_contracts.memory import AccessContext
import test_instruction_memory as p1a
from test_compaction_fixture import pg43, seed_chat


@pytest.fixture
def successor_private(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        connection.execute(text("UPDATE workspace_memberships SET role='member' WHERE id=:id"),
                           {"id": scope.membership_id})
        connection.execute(text("""INSERT INTO workspace_memberships
            (id,workspace_id,user_id,role,created_at) VALUES (:id,:workspace,:user,'owner',now())"""),
            {"id": str(uuid4()), "workspace": scope.workspace_id, "user": scope.other_user_id})
    return pg43, AccessContext(scope.user_id, scope.workspace_id, "management", "private"), scope.other_user_id


@pytest.mark.parametrize("oracle", [
    "test_create_replay_conflict_lost_ack_and_owner_privacy",
    "test_all_revision_conditions_erasure_and_replay",
    "test_correction_cas_race_and_shared_instruction_preservation",
    "test_same_key_concurrent_one_mutation",
    "test_invalidation_preserves_intent_and_source_validity",
    "test_erased_restore_and_retained_fk_rejected",
    "test_revocation_archive_and_cross_workspace_fail_closed",
    "test_deleted_identity_cannot_append_live_head",
    "test_commit_ack_loss_reconciles_without_duplicate",
    "test_archive_blocks_all_private_management",
    "test_failed_delete_rolls_back_all_erasure",
    "test_shared_source_retained_until_last_dependent_erased",
    "test_cross_owner_and_cross_workspace_support_sql_rejected",
    "test_forged_revision_hash_rejected",
])
def test_p1a_commands_on_successor(successor_private, oracle):
    getattr(p1a, oracle)(successor_private)


@pytest.mark.parametrize("sql", p1a.test_illegal_sql_rejected.pytestmark[0].args[1])
def test_p1a_illegal_sql_stays_rejected(successor_private, sql):
    p1a.test_illegal_sql_rejected(successor_private, sql)


@pytest.mark.parametrize("conditions", p1a.test_insert_malformed_conditions_rejected.pytestmark[0].args[1])
def test_p1a_malformed_conditions_stay_rejected(successor_private, conditions):
    p1a.test_insert_malformed_conditions_rejected(successor_private, conditions)


@pytest.mark.parametrize("role", p1a.test_unknown_member_roles_fail_closed.pytestmark[0].args[1])
def test_p1a_unknown_member_roles_stay_rejected(successor_private, role):
    p1a.test_unknown_member_roles_fail_closed(successor_private, role)


@pytest.mark.parametrize("head_first", [False, True])
@pytest.mark.parametrize("terminal_action", ["deactivate", "correct", "delete"])
def test_p1a_terminal_fence_stays_independent_of_write_order(successor_private, head_first, terminal_action):
    p1a.test_intent_fence_independent_of_sql_write_order(successor_private, head_first, terminal_action)
