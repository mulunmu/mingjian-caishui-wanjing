"""enterprise_id 映射 + MySQL 编码自检"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.enterprise_id import describe_taxpayer_id, enterprise_id_of, mysql_taxpayer_id


def test_enterprise_id_md5_passthrough():
    tid = "0039fa8febbd8593f36ec19219685382"
    assert enterprise_id_of(tid) == tid
    assert mysql_taxpayer_id(tid) == tid


def test_enterprise_id_plain_tax_hash():
    plain = "91110000MA01234567"
    eid = enterprise_id_of(plain)
    assert len(eid) == 32
    assert eid != plain


def test_describe_taxpayer_id():
    d = describe_taxpayer_id("0039fa8febbd8593f36ec19219685382")
    assert d["is_md5_hex"] is True
    assert d["format"] == "md5_hex"
