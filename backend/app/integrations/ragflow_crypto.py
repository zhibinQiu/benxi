"""RAGFlow 登录密码 RSA 加密（与 KnowFlow Web 公钥一致）。"""

from __future__ import annotations

import base64

from Cryptodome.Cipher import PKCS1_v1_5
from Cryptodome.PublicKey import RSA

_RAGFLOW_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArq9XTUSeYr2+N1h3Afl/z8Dse/2yD0ZGrKwx+EEEcdsBLca9Ynmx3nIB5obmLlSfmskLpBo0UACBmB5rEjBp2Q2f3AG3Hjd4B+gNCG6BDaawuDlgANIhGnaTLrIqWrrcm4EMzJOnAOI1fgzJRsOOUEfaS318Eq9OVO3apEyCCt0lOQK6PuksduOjVxtltDav+guVAA068NrPYmRNabVKRNLJpL8w4D44sfth5RvZ3q9t+6RTArpEtc5sh5ChzvqPOzKGMXW83C95TxmXqpbK6olN4RevSfVjEAgCydH6HN6OhtOQEcnrU97r9H0iZOWwbw3pVrZiUkuRD1R56Wzs2wIDAQAB
-----END PUBLIC KEY-----"""


def rsa_encrypt_password(password: str) -> str:
    rsa_key = RSA.import_key(_RAGFLOW_PUBLIC_KEY)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(base64.b64encode(password.encode()))
    return base64.b64encode(encrypted).decode()
