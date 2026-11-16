import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote,urlencode

PERIOD=30
DIGITS=6
ISSUER='KTEL Platform'


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code(secret,step):
    key=base64.b32decode(secret,casefold=True)
    mac=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest()
    offset=mac[-1]&0x0F
    value=struct.unpack('>I',mac[offset:offset+4])[0]&0x7FFFFFFF
    return str(value%10**DIGITS).zfill(DIGITS)


def matching_step(secret,candidate,now=None):
    if len(candidate)!=DIGITS or not candidate.isascii() or not candidate.isdigit():
        return None
    current=int((time.time() if now is None else now)//PERIOD)
    matched=None
    for step in (current-1,current,current+1):
        if step>=0 and hmac.compare_digest(code(secret,step),candidate):
            matched=step
    return matched


def verify(secret:str,code:str,now:float|None=None)->bool:
    return matching_step(secret,code,now) is not None


def otpauth_uri(secret,email):
    label=quote(f'{ISSUER}:{email}',safe='')
    return f'otpauth://totp/{label}?'+urlencode({'secret':secret,'issuer':ISSUER,'algorithm':'SHA1','digits':DIGITS,'period':PERIOD})
