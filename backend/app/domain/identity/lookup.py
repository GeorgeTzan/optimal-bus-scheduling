"""Narrow identity discovery before trusted tenant context can be installed."""
from sqlalchemy import text,func
from db.models import User


def lookup_identity(db, identity, *, login=False):
    if db.get_bind().dialect.name == 'postgresql':
        function='ktel_login_identity' if login else 'ktel_token_identity'
        # The function name is selected only from constants; identity is a bound value.
        return db.query(User).from_statement(text(f'SELECT * FROM public.{function}(:identity)')).params(identity=str(identity)).first()
    # SQLite compatibility for isolated unit tests; real tenant boundaries are tested on PostgreSQL.
    if not login and str(identity).isdigit():
        return db.query(User).filter(User.id==int(identity)).first()
    if login:
        return db.query(User).filter(func.lower(func.trim(User.email))==str(identity).strip().lower()).first()
    return db.query(User).filter(User.email==str(identity)).first()
