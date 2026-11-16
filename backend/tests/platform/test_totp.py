import base64
import re
from urllib.parse import urlsplit,parse_qs
import pytest
from app.domain.platform import totp

RFC_SECRET='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


@pytest.mark.parametrize('moment,code',[(59,'287082'),(1111111109,'081804'),(1111111111,'050471'),(1234567890,'005924'),(2000000000,'279037')])
def test_rfc6238_sha1_vectors(moment,code):
    assert totp.verify(RFC_SECRET,code,now=moment)


def test_adjacent_steps_are_accepted_and_two_steps_away_refused():
    code='081804'
    assert totp.verify(RFC_SECRET,code,now=1111111109+30)
    assert totp.verify(RFC_SECRET,code,now=1111111109-30)
    assert not totp.verify(RFC_SECRET,code,now=1111111109+60)
    assert not totp.verify(RFC_SECRET,code,now=1111111109-60)


def test_matched_step_is_reported_for_replay_protection():
    assert totp.matching_step(RFC_SECRET,'081804',now=1111111109)==1111111109//30
    assert totp.matching_step(RFC_SECRET,'081804',now=1111111109+30)==1111111109//30
    assert totp.matching_step(RFC_SECRET,'000000',now=1111111109) is None


@pytest.mark.parametrize('code',['','12345','1234567','abcdef',' 81804','081804\n'])
def test_malformed_codes_are_refused(code):
    assert not totp.verify(RFC_SECRET,code,now=1111111109)


def test_new_secret_is_random_base32_of_160_bits():
    first,second=totp.new_secret(),totp.new_secret()
    assert first!=second
    assert re.fullmatch('[A-Z2-7]{32}',first)
    assert len(base64.b32decode(first))==20


def test_otpauth_uri_names_issuer_account_and_secret():
    uri=totp.otpauth_uri(RFC_SECRET,'ops@example.org')
    parts=urlsplit(uri)
    assert parts.scheme=='otpauth' and parts.netloc=='totp'
    assert 'ops%40example.org' in parts.path
    query=parse_qs(parts.query)
    assert query['secret']==[RFC_SECRET]
    assert query['algorithm']==['SHA1'] and query['digits']==['6'] and query['period']==['30']
