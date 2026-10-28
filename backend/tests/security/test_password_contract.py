from datetime import datetime,timedelta,timezone
import bcrypt
from core.security import hash_password,verify_password,create_access_token,decode_token


def test_long_unicode_passwords_are_not_silently_truncated():
    first='κ'*40+'-first-long-password'
    other='κ'*40+'-other-long-password'
    hashed=hash_password(first)
    assert verify_password(first,hashed)
    assert not verify_password(other,hashed)


def test_existing_bcrypt_seeded_password_remains_supported():
    legacy=bcrypt.hashpw(b'admin123',bcrypt.gensalt()).decode()
    assert verify_password('admin123',legacy)
    assert not verify_password('different',legacy)


def test_bearer_token_respects_server_session_expiry():
    expires=datetime.now(timezone.utc)+timedelta(minutes=5)
    encoded=create_access_token({'sub':'1','sid':'session','exp':expires})
    assert decode_token(encoded)['exp']==int(expires.timestamp())
