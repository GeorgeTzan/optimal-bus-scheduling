from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from db.database import get_db
from app.domain.identity.permissions import require_permission
from app.domain.reports import service
from app.domain.reports.coverage import line_days

router = APIRouter(prefix='/api/v1/reports', tags=['Reports'])


@router.get('/monthly')
def get_monthly(month: str = Query(), user=Depends(require_permission('reports.read')), db: Session = Depends(get_db)):
    return service.monthly(db, user, service.requested_month(db, user.ktel_id, month))


@router.get('/coverage/line')
def get_line(month: str = Query(), line: str = Query(), user=Depends(require_permission('reports.read')), db: Session = Depends(get_db)):
    return line_days(db, user.ktel_id, service.requested_month(db, user.ktel_id, month), line)


MEDIA = {'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'pdf': 'application/pdf'}


@router.get('/export')
def get_export(month: str = Query(), format: Literal['xlsx', 'pdf'] = Query(), lang: Literal['el', 'en'] = Query('el'),
               user=Depends(require_permission('reports.read')), db: Session = Depends(get_db)):
    chosen = service.requested_month(db, user.ktel_id, month)
    content = service.export(db, user, chosen, format, lang)
    return Response(content, media_type=MEDIA[format], headers={'Content-Disposition': f'attachment; filename="reports-{chosen:%Y-%m}.{format}"'})
