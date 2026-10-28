"""Encrypted identity email outbox. Queueing is never reported as successful delivery."""
import base64,hashlib,json,logging,smtplib,ssl
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from uuid import uuid4
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import or_,text
from config import settings
from app.domain.identity.models import EmailOutbox,IdentityToken
from app.domain.identity.tenant_session import tenant_transaction


def _cipher():
    key=settings.EMAIL_OUTBOX_KEY or base64.urlsafe_b64encode(hashlib.sha256(
        ('ktel-email-outbox-v1:'+settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(key.encode())


def decrypt_payload(value):
    return json.loads(_cipher().decrypt(value.encode()))


def enqueue_identity_email(db,token,secret,organization_name):
    invitation=token.kind=='invitation'
    path='accept-invitation' if invitation else 'reset-password'
    link=f'{settings.PUBLIC_APP_URL}/{path}#token={secret}'
    subject=f'Πρόσκληση στο {organization_name}' if invitation else 'Επαναφορά κωδικού KTEL'
    body=(f'Έχετε προσκληθεί στο {organization_name}. Ο σύνδεσμος ισχύει για 48 ώρες.' if invitation
          else 'Ζητήσατε νέο κωδικό για το KTEL. Ο σύνδεσμος ισχύει για 30 λεπτά. Αν δεν το ζητήσατε, αγνοήστε το μήνυμα.')
    payload={'to':token.email,'subject':subject,'text':body+'\n\n'+link,'link':link}
    row=EmailOutbox(id=str(uuid4()),tenant_id=token.tenant_id,identity_token_id=token.id,kind=token.kind,
        encrypted_payload=_cipher().encrypt(json.dumps(payload,ensure_ascii=False).encode()).decode(),
        delivery_status='queued' if settings.SMTP_HOST and settings.SMTP_FROM else 'not_configured')
    db.add(row);db.flush()
    return row


def send_email(payload,message_id):
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise RuntimeError('SMTP is not configured')
    message=EmailMessage()
    message['From']=settings.SMTP_FROM;message['To']=payload['to'];message['Subject']=payload['subject']
    message['Message-ID']=f'<{message_id}@ktel-outbox>'
    message.set_content(payload['text'])
    with smtplib.SMTP(settings.SMTP_HOST,settings.SMTP_PORT,timeout=10) as smtp:
        smtp.ehlo()
        if settings.SMTP_USE_TLS:
            smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME,settings.SMTP_PASSWORD)
        smtp.send_message(message)


def deliver_once(factory,tenant_id,worker_id):
    now=datetime.now(timezone.utc)
    with factory() as db,tenant_transaction(db,tenant_id):
        row=db.query(EmailOutbox).filter(EmailOutbox.delivery_status.in_(['queued','delivering']),
            or_(EmailOutbox.lease_expires_at.is_(None),EmailOutbox.lease_expires_at<now),EmailOutbox.attempts<5
        ).order_by(EmailOutbox.created_at).with_for_update(skip_locked=True).first()
        if row is None:
            return False
        token=db.query(IdentityToken).filter_by(id=row.identity_token_id).first()
        expires=token.expires_at if token and token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc) if token else now
        if not token or token.consumed_at is not None or expires<=now:
            row.delivery_status='discarded';db.commit();return True
        try:
            payload=decrypt_payload(row.encrypted_payload)
        except (InvalidToken,ValueError):
            # Unreadable (for example the encryption key changed): final for this message, and it must not block the others.
            row.delivery_status='failed';row.lease_expires_at=None;db.commit();return True
        row.delivery_status='delivering';row.worker_id=worker_id;row.attempt_token+=1;row.attempts+=1
        row.lease_expires_at=now+timedelta(seconds=30)
        identifier,attempt=row.id,row.attempt_token
        db.commit()
    status='sent'
    try:
        send_email(payload,identifier)
    except (smtplib.SMTPException,OSError,RuntimeError,ValueError):
        status='failed'
    with factory() as db,tenant_transaction(db,tenant_id):
        row=db.query(EmailOutbox).filter_by(id=identifier,worker_id=worker_id,attempt_token=attempt,
                                         delivery_status='delivering').with_for_update().first()
        if row:
            row.delivery_status=status;row.lease_expires_at=None
            if status=='sent':
                row.sent_at=datetime.now(timezone.utc)
            db.commit()
    return True


def pending_mail_tenants(db):
    """Ids of organizations with deliverable mail, from a narrow function that reads nothing else."""
    return [row[0] for row in db.execute(text('SELECT public.ktel_mail_tenants()')).all()]


def deliver_all_once(factory,worker_id):
    """One pass over every organization with mail waiting; True if anything was attempted."""
    with factory() as db:
        tenants=pending_mail_tenants(db)
    worked=False
    for tenant_id in tenants:
        try:
            worked=deliver_once(factory,tenant_id,worker_id) or worked
        except Exception:  # one organization's database problem must not stop mail for the others; nothing from the message is logged
            logging.getLogger(__name__).error('Mail delivery failed for organization %s',tenant_id)
    return worked
