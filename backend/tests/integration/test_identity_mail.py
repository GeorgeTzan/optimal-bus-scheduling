import socketserver,threading
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from config import settings
from tests.integration.test_identity import identity_setup


@contextmanager
def smtp_sink(reject=False):
    received=[]
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 local-test SMTP\r\n')
            while line:=self.rfile.readline():
                command=line.decode().strip().upper()
                if command.startswith(('EHLO','HELO')):
                    self.wfile.write(b'250-local-test\r\n250 8BITMIME\r\n')
                elif command.startswith(('MAIL','RCPT','RSET','NOOP')):
                    self.wfile.write(b'250 OK\r\n')
                elif command=='DATA':
                    self.wfile.write(b'354 End with dot\r\n');body=[]
                    while (line:=self.rfile.readline()) not in (b'.\r\n',b''):
                        body.append(line)
                    if reject:
                        self.wfile.write(b'451 Temporary test rejection\r\n')
                    else:
                        received.append(b''.join(body));self.wfile.write(b'250 Accepted\r\n')
                elif command=='QUIT':
                    self.wfile.write(b'221 Bye\r\n');break
                else:
                    self.wfile.write(b'500 Unsupported test command\r\n')
    with socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            yield server.server_address[1],received
        finally:
            server.shutdown();thread.join(timeout=2)


def test_real_local_smtp_delivery_uses_encrypted_outbox_and_preserves_failure_state(identity_setup,restricted_databases,monkeypatch):
    from app.domain.identity.service import issue_invitation
    from app.domain.identity.mail import deliver_once
    tenant=identity_setup['first'].tenant_id
    for reject in (False,True):
        with smtp_sink(reject) as (port,received):
            monkeypatch.setattr(settings,'SMTP_HOST','127.0.0.1')
            monkeypatch.setattr(settings,'SMTP_PORT',port)
            monkeypatch.setattr(settings,'SMTP_FROM','sender@example.org')
            monkeypatch.setattr(settings,'SMTP_USE_TLS',False)
            with identity_setup['owner_factory']() as db:
                invitation=issue_invitation(db,tenant,f'recipient{reject}@example.org','viewer');db.commit()
            assert deliver_once(sessionmaker(bind=restricted_databases['worker']),tenant,'smtp-test')
            with identity_setup['owner_factory']() as db:
                row=db.execute(text("SELECT delivery_status,encrypted_payload,sent_at FROM domain_email_outbox WHERE tenant_id=:tenant AND delivery_status IN ('sent','failed') ORDER BY created_at DESC LIMIT 1"),{'tenant':tenant}).one()
                assert row.delivery_status==('failed' if reject else 'sent')
                assert (row.sent_at is None)==reject
                assert invitation.token not in row.encrypted_payload
            assert len(received)==(0 if reject else 1)
            if received:
                assert b'Message-ID:' in received[0]
