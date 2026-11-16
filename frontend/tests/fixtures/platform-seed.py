import json,secrets,sys,uuid
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from config import settings
from app.domain.platform.service import create_operator

engine=create_engine(settings.DATABASE_URL,hide_parameters=True)
try:
    if sys.argv[1]=='create':
        email=f'browser-operator-{uuid.uuid4().hex}@example.org';password=secrets.token_urlsafe(18)
        with sessionmaker(bind=engine)() as db:
            secret=create_operator(db,email=email,password=password)
        print(json.dumps({'email':email,'password':password,'secret':secret}))
    elif sys.argv[1]=='fail-mail':
        with engine.begin() as connection:
            updated=connection.execute(text("UPDATE domain_email_outbox SET delivery_status='failed' WHERE tenant_id=:id AND tenant_id IN (SELECT id FROM ktels WHERE name LIKE 'Browser identity test %')"),{'id':int(sys.argv[2])}).rowcount
        print(json.dumps({'failed':updated}))
    elif sys.argv[1]=='cleanup':
        email=sys.argv[2]
        if not email.startswith('browser-operator-'):raise ValueError('Refusing an unrelated operator')
        with engine.begin() as connection:
            operator=connection.execute(text('SELECT id FROM platform_operators WHERE email=:email'),{'email':email}).scalar_one()
            tenants=connection.execute(text("SELECT DISTINCT tenant_id FROM platform_audit WHERE operator_id=:id AND action='customer_created'"),{'id':operator}).scalars().all()
            connection.execute(text('DELETE FROM platform_audit WHERE operator_id=:id'),{'id':operator})
            connection.execute(text('DELETE FROM platform_support_sessions WHERE operator_id=:id'),{'id':operator})
            connection.execute(text('DELETE FROM platform_sessions WHERE operator_id=:id'),{'id':operator})
            connection.execute(text('DELETE FROM platform_operators WHERE id=:id'),{'id':operator})
        print(json.dumps({'tenants':tenants}))
finally:engine.dispose()
