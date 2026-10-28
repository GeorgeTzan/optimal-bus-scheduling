"""Anonymous budgets persist across API workers without storing email or IP addresses."""
from datetime import datetime,timedelta,timezone
import hashlib,hmac
from sqlalchemy import text
from config import settings
from app.domain.identity.models import IdentityRateLimit


def consume_budget(db,action,email,address,limit,seconds):
    key=hmac.new(settings.SECRET_KEY.encode(),f'{action}:{email.strip().lower()}:{address}'.encode(),hashlib.sha256).hexdigest()
    if db.get_bind().dialect.name=='postgresql':
        allowed=db.execute(text('SELECT public.ktel_auth_budget(:key,:seconds,:limit)'),
                           {'key':key,'seconds':seconds,'limit':limit}).scalar_one()
    else:
        now=datetime.now(timezone.utc)
        row=db.query(IdentityRateLimit).filter_by(key_hash=key).first()
        if row is None:
            row=IdentityRateLimit(key_hash=key,window_start=now,attempts=0);db.add(row)
        start=row.window_start.replace(tzinfo=timezone.utc) if row.window_start.tzinfo is None else row.window_start
        if start<now-timedelta(seconds=seconds):
            row.window_start=now;row.attempts=0
        row.attempts+=1
        allowed=row.attempts<=limit
    # This public-auth gate runs before identity mutations; failed logins must not roll back the counter.
    db.commit()
    return allowed
