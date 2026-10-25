import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.crowdfunding.audit.analyzer import analyze_documents
from app.domains.crowdfunding.audit.models import ProjectAudit
from app.domains.crowdfunding.audit.schemas import ProjectAuditResponse
from app.domains.crowdfunding.audit.scoring import capital_and_cash
from app.domains.crowdfunding.models import ProjectDocument
from app.domains.crowdfunding.repository import project_for_user
from app.domains.crowdfunding.schemas import ProjectDocumentResponse
from app.domains.identity.dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
Files = Annotated[list[UploadFile], File()]

MAX_FILES = 5
MAX_FILE_SIZE = 10 * 1024 * 1024


async def _read_pdfs(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} fichiers autorisés")
    contents = []
    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Fichier '{upload.filename}' n'est pas un PDF")
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, f"Fichier '{upload.filename}' dépasse 10 MB")
        contents.append((upload.filename, content))
    return contents


@router.post("/analyze", response_model=ProjectAuditResponse, status_code=201)
@limiter.limit("3/minute")
async def analyze(
    request: Request,
    files: Files,
    user: CurrentUser,
    session: Session,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    project_id_form: Annotated[uuid.UUID | None, Form(alias="project_id")] = None,
) -> ProjectAudit:
    """Audit de risque de PDF, rattaché au projet de l'utilisateur passé en champ de formulaire ou en paramètre."""
    target = project_id_form or project_id
    if target is not None:
        await project_for_user(session, target, user.id)
    contents = await _read_pdfs(files)
    total_capital, cash = await capital_and_cash(session, user.id)
    try:
        audit = await analyze_documents(session, contents, user.id, target, cash, total_capital)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.error("Analyze error: %s", exc, exc_info=True)
        raise HTTPException(500, f"Erreur interne lors de l'analyse : {exc}") from exc
    await session.commit()
    await session.refresh(audit)
    return audit


@router.get("/audits", response_model=list[ProjectAuditResponse])
@limiter.limit("30/minute")
async def list_audits(request: Request, user: CurrentUser, session: Session) -> list[ProjectAudit]:
    """Audits de l'utilisateur, du plus récent au plus ancien."""
    result = await session.execute(
        select(ProjectAudit).where(ProjectAudit.user_id == user.id).order_by(ProjectAudit.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/documents/{doc_id}/download")
@limiter.limit("30/minute")
async def download_document(
    request: Request, doc_id: uuid.UUID, user: CurrentUser, session: Session
) -> StreamingResponse:
    """PDF joint à un projet de l'utilisateur."""
    result = await session.execute(
        select(ProjectDocument).where(ProjectDocument.id == doc_id, ProjectDocument.user_id == user.id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(404, "Document non trouvé")
    return StreamingResponse(
        io.BytesIO(document.file_data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{document.file_name}"'},
    )


@router.post("/{project_id}/documents", response_model=list[ProjectDocumentResponse], status_code=201)
@limiter.limit("10/minute")
async def upload_documents(
    request: Request, project_id: uuid.UUID, files: Files, user: CurrentUser, session: Session
) -> list[ProjectDocument]:
    """Joint des PDF à un projet de l'utilisateur."""
    project = await project_for_user(session, project_id, user.id)
    documents = [
        ProjectDocument(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user.id,
            file_name=name,
            file_data=data,
            file_size=len(data),
        )
        for name, data in await _read_pdfs(files)
    ]
    session.add_all(documents)
    await session.commit()
    for document in documents:
        await session.refresh(document)
    return documents
