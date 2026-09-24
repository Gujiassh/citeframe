from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.models import Asset, ContentUnitEmbedding
from ai_pdf_api.services.embedding_index import assert_current_embeddings_match_contract, connection_index_contract
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_api.services.workspace_models import resolve_connection


def reindex_asset_ids(db: Session, workspace_id: str, connection=None) -> list[str]:
    contract = connection_index_contract(connection or resolve_connection(db, workspace_id, "embedding"))
    ids = db.scalars(select(Asset.id).join(ContentUnitEmbedding, ContentUnitEmbedding.asset_id == Asset.id).where(
        Asset.workspace_id == workspace_id, Asset.deleted_at.is_(None), Asset.status == "ready",
        ContentUnitEmbedding.is_current.is_(True)).distinct()).all()
    mismatched = []
    for asset_id in ids:
        try:
            assert_current_embeddings_match_contract(db, workspace_id, contract, asset_ids=[asset_id])
        except ModelProviderError as error:
            if error.code != "embedding_index_mismatch":
                raise
            mismatched.append(asset_id)
    return sorted(mismatched)
