"""Disposable local browser-test organization, never uses the configured runtime role."""
import json,sys,uuid
from sqlalchemy import create_engine,text,MetaData
from sqlalchemy.orm import sessionmaker
from config import settings
from app.domain.identity.service import provision_organization

engine=create_engine(settings.DATABASE_URL,hide_parameters=True)
try:
    if sys.argv[1]=='create':
        suffix=uuid.uuid4().hex
        with sessionmaker(bind=engine)() as db:
            invite=provision_organization(db,name='Browser identity test '+suffix,admin_email=suffix+'@example.org')
            print(json.dumps({'tenant_id':invite.tenant_id,'token':invite.token,'email':invite.email}))
    elif sys.argv[1]=='invite':
        from app.domain.identity.service import issue_invitation
        tenant_id=int(sys.argv[2]);role=sys.argv[3]
        with sessionmaker(bind=engine)() as db:
            name=db.execute(text('SELECT name FROM ktels WHERE id=:id'),{'id':tenant_id}).scalar_one()
            if not name.startswith('Browser identity test '):raise ValueError('Refusing an unrelated organization')
            invitation=issue_invitation(db,tenant_id,uuid.uuid4().hex+'@example.org',role);db.commit()
            print(json.dumps({'token':invitation.token}))
    elif sys.argv[1]=='mail':
        # Reads the queued invitation for one address from the local mail outbox; email is not sent anywhere.
        from urllib.parse import parse_qs,urlsplit
        from app.domain.identity.mail import decrypt_payload
        tenant_id=int(sys.argv[2]);email=sys.argv[3]
        with engine.connect() as connection:
            name=connection.execute(text('SELECT name FROM ktels WHERE id=:id'),{'id':tenant_id}).scalar_one()
            if not name.startswith('Browser identity test '):raise ValueError('Refusing an unrelated organization')
            rows=connection.execute(text("SELECT encrypted_payload FROM domain_email_outbox WHERE tenant_id=:t AND kind='invitation' ORDER BY created_at DESC"),{'t':tenant_id}).all()
        link=next(data['link'] for (payload,) in rows if (data:=decrypt_payload(payload))['to']==email)
        print(json.dumps({'token':parse_qs(urlsplit(link).fragment)['token'][0]}))
    elif sys.argv[1]=='cleanup':
        tenant_id=int(sys.argv[2]);metadata=MetaData();metadata.reflect(engine)
        with engine.begin() as connection:
            name=connection.execute(text('SELECT name FROM ktels WHERE id=:id FOR UPDATE'),{'id':tenant_id}).scalar_one()
            if not name.startswith('Browser identity test '):raise ValueError('Refusing to remove an unrelated organization')
            for table in reversed(metadata.sorted_tables):
                scope=next((table.c[key] for key in ('tenant_id','ktel_id') if key in table.c),None)
                if scope is not None:connection.execute(table.delete().where(scope==tenant_id))
            connection.execute(metadata.tables['ktels'].delete().where(metadata.tables['ktels'].c.id==tenant_id))
finally:engine.dispose()
