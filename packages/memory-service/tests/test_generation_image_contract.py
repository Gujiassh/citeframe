"""Isolated image structure; no provider or native activation."""
import base64
from dataclasses import FrozenInstanceError, asdict, fields
from hashlib import sha256
import json
import struct
import traceback
import tracemalloc
from unittest.mock import Mock
from zlib import crc32
import pytest
import citeframe_contracts
from citeframe_contracts import memory as c
from citeframe_contracts.memory import GenerationImage, GenerationMessage, GenerationRequest, ProtocolError

B, E = 4194304, 5592408

def header(w=1, h=1, depth=8, color=6, compression=0, filter_=0, interlace=0):
    chunk = b"IHDR" + struct.pack(">IIBBBBB", w, h, depth, color, compression, filter_, interlace)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + struct.pack(">I", crc32(chunk))

def encode(raw):
    return base64.b64encode(raw).decode("ascii")

def image(value, **changes):
    args = dict(media_type="image/png", data_base64=value, width=1, height=1, detail="high")
    args.update(changes)
    return GenerationImage(**args)

def spies(monkeypatch, forbid=False):
    result = []
    for owner, name in ((c, "_image_ascii"), (c.base64, "b64decode"), (c.base64, "b64encode")):
        spy = Mock(side_effect=AssertionError("early_conversion")) if forbid else Mock(wraps=getattr(owner, name))
        monkeypatch.setattr(owner, name, spy)
        result.append(spy)
    return result

def test_constants_export_text_compatibility():
    assert citeframe_contracts.GenerationImage is GenerationImage
    assert "GenerationImage" in citeframe_contracts.__all__
    assert c.GENERATION_IMAGE_STRUCTURE_VERSION == "generation-image-structure-v1"
    assert c.GENERATION_IMAGE_MAX_DECODED_BYTES == B
    assert c.GENERATION_IMAGE_MAX_ENCODED_CHARS == E == 4*((B+2)//3)
    assert c.GENERATION_MESSAGE_MAX_IMAGES == 8
    assert c.GENERATION_IMAGE_MAX_DIMENSION == 2**31-1
    assert [f.name for f in fields(GenerationMessage)] == ["role", "content", "tool_calls", "tool_call_id"]
    req = GenerationRequest((GenerationMessage("user", "hello", (), None),), 128)
    raw = json.dumps(asdict(req), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert sha256(raw.encode()).hexdigest() == "6a4c0a68b219e50238694606c3408d5e82b12ac1311e00bcd9816342216b5c21"

@pytest.mark.parametrize("size", [33,34,35,65536,B])
def test_real_cap_peak_and_single_conversion(size, monkeypatch):
    value = encode(header()+b"x"*(size-33))
    if size == B:
        assert len(value) == E and value.endswith("==")
    calls = spies(monkeypatch)
    tracemalloc.start()
    try:
        result = image(value)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.data_base64 == value
    assert peak <= 32*1024*1024
    assert [s.call_count for s in calls] == [1,1,1]
    print(f"decoded={size} encoded={len(value)} additional_tracked_peak={peak}")

@pytest.mark.parametrize("case", ["E+1","B+1","B+2","short"])
def test_real_overflow_zero_conversion_or_downstream(case, monkeypatch):
    if case == "E+1":
        value = "A"*(E+1)
    elif case == "short":
        value = "A"*40
    else:
        size = B+(1 if case == "B+1" else 2)
        value = encode(header()+b"x"*(size-33))
        assert len(value) == E
    calls = spies(monkeypatch, True)
    profile, counter, provider = Mock(), Mock(), Mock()
    with pytest.raises(ProtocolError, match="^generation_input_unsupported$"):
        result = image(value)
        profile(result)
        counter(result)
        provider(result)
    assert not any(s.called for s in calls)
    for call in (profile,counter,provider):
        call.assert_not_called()

@pytest.mark.parametrize("changes", [
    {"media_type":b"image/png"},{"media_type":"image/jpeg"},{"detail":"auto"},
    {"detail":None},{"width":True},{"height":False},{"width":0},{"height":-1},
    {"width":2**31},{"height":1.0},{"data_base64":b"bad"},{"data_base64":["bad"]},
])
def test_types_before_conversion(changes,monkeypatch):
    value = encode(header())
    calls = spies(monkeypatch,True)
    with pytest.raises(ProtocolError):
        image(value,**changes)
    assert not any(s.called for s in calls)

@pytest.mark.parametrize("prefix", ["é","="," ","\n"])
def test_alphabet_before_conversion(prefix,monkeypatch):
    value = prefix+encode(header())[1:]
    calls = spies(monkeypatch,True)
    with pytest.raises(ProtocolError):
        image(value)
    assert not any(s.called for s in calls)

@pytest.mark.parametrize("size,padding", [(34,2),(35,1)])
def test_noncanonical_pad_bits(size,padding):
    value = encode(header()+b"x"*(size-33))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    offset = len(value)-padding-1
    bad = value[:offset]+alphabet[alphabet.index(value[offset])+1]+value[offset+1:]
    assert base64.b64decode(bad,validate=True)==base64.b64decode(value,validate=True)
    with pytest.raises(ProtocolError):
        image(bad)

@pytest.mark.parametrize("raw", [
    header()[:32],b"not-PNG!"+header()[8:],
    header()[:8]+b"\xff\xff\xff\xff"+header()[12:],
    header()[:12]+b"IDAT"+header()[16:],header()[:29]+b"\0\0\0\0",
    header(w=2),header(h=2),header(depth=3),header(color=1),
    header(compression=1),header(filter_=1),header(interlace=2),
])
def test_fixed_ihdr_rejects(raw):
    with pytest.raises(ProtocolError):
        image(encode(raw))

@pytest.mark.parametrize("color,depth", [
    (0,1),(0,2),(0,4),(0,8),(0,16),(2,8),(2,16),(3,1),(3,2),(3,4),(3,8),
    (4,8),(4,16),(6,8),(6,16),
])
def test_legal_ihdr_only_is_not_full_png_validation(color,depth):
    value = encode(header(color=color,depth=depth,interlace=1))
    assert image(value).data_base64 == value

def test_crc_fixed_input_and_structural_dimension_max(monkeypatch):
    raw = header(w=2**31-1,h=2**31-1)+b"unparsed remainder"
    value = encode(raw)
    spy = Mock(wraps=c.crc32)
    monkeypatch.setattr(c,"crc32",spy)
    image(value,width=2**31-1,height=2**31-1)
    spy.assert_called_once_with(raw[12:29])
    assert len(spy.call_args.args[0]) == 17

def test_privacy_and_immutability(monkeypatch,caplog):
    value = encode(header()+b"PRIVATE_IMAGE_MARKER")
    result = image(value)
    with pytest.raises(FrozenInstanceError):
        result.width = 2
    assert value not in repr(result)
    assert value not in repr({"nested":(result,)})
    monkeypatch.setattr(c.base64,"b64decode",Mock(side_effect=ValueError(value)))
    with pytest.raises(ProtocolError) as caught:
        image(value)
    rendered = "".join(traceback.format_exception(caught.type,caught.value,caught.tb))
    assert str(caught.value) == "generation_input_unsupported"
    assert caught.value.__suppress_context__
    assert value not in rendered and value not in caplog.text

def test_padding_rejected_before_conversion(monkeypatch):
    value = encode(header()+b"x")
    calls = spies(monkeypatch,True)
    with pytest.raises(ProtocolError):
        image(value[:-3]+"===")
    assert not any(s.called for s in calls)

def test_scan_once_and_no_scan_before_length_gate(monkeypatch):
    alphabet = c._IMAGE_BASE64_ALPHABET
    class ObservedAlphabet:
        def __init__(self):
            self.visits = 0
        def __contains__(self, char):
            self.visits += 1
            return char in alphabet
    observed = ObservedAlphabet()
    monkeypatch.setattr(c,"_IMAGE_BASE64_ALPHABET",observed)
    value = encode(header()+b"x")
    image(value)
    assert observed.visits == len(value)-2
    observed.visits = 0
    with pytest.raises(ProtocolError):
        image("A"*(E+1))
    assert observed.visits == 0
