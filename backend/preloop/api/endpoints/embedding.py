from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from preloop.models.db.session import get_db_session as get_db
from preloop.models.crud.embedding import CRUDIssueEmbedding
from preloop.schemas.embedding import EmbeddingRawResponse, EmbeddingRawDataItem
from preloop.models.models.user import User

from preloop.api.auth import get_current_active_user


router = APIRouter()


@router.get(
    "/embeddings",
    response_model=EmbeddingRawResponse,
    summary="Get all issue embeddings",
    tags=["embeddings"],
)
def get_raw_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    embedding_model_id: Optional[str] = Query(
        None, description="The ID of the embedding model to use."
    ),
    project_ids: Optional[str] = Query(
        None, description="Comma-separated list of project IDs."
    ),
    project_names: Optional[str] = Query(
        None, description="Comma-separated list of project names."
    ),
    organization_ids: Optional[str] = Query(
        None, description="Comma-separated list of organization IDs."
    ),
    organization_names: Optional[str] = Query(
        None, description="Comma-separated list of organization names."
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        1000, ge=1, le=2000, description="Maximum number of records to return."
    ),
):
    """
    API endpoint to fetch raw embedding vectors for issues, with optional filtering.
    This endpoint is designed to provide data for frontend visualizations like deck.gl.
    """
    crud_embedding = CRUDIssueEmbedding(db)

    project_id_list = project_ids.split(",") if project_ids else None
    project_name_list = project_names.split(",") if project_names else None
    organization_id_list = organization_ids.split(",") if organization_ids else None
    organization_name_list = (
        organization_names.split(",") if organization_names else None
    )

    raw_data = crud_embedding.get_raw_embeddings(
        db=db,
        account_id=str(current_user.account_id),
        embedding_model_id=embedding_model_id,
        project_ids=project_id_list,
        project_names=project_name_list,
        organization_ids=organization_id_list,
        organization_names=organization_name_list,
        skip=skip,
        limit=limit,
    )

    # Transform the list of tuples into a list of EmbeddingRawDataItem objects
    formatted_data = [
        EmbeddingRawDataItem(
            issue_id=item[0],
            embedding=item[1],
            issue_title=item[2],
            project_id=item[3],
            issue_type=item[4],
            issue_created_at=item[5],
        )
        for item in raw_data
    ]

    return EmbeddingRawResponse(data=formatted_data)
