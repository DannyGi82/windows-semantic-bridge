import base64,io,json
import pytest
from PIL import Image
from munim_rpc import check_allowed, extract_text, validate_capture, MunimError

def test_denies_actions_by_default():
    for name in ['click','type_text','set_value','browser_navigate','activate_app','drag']:
        with pytest.raises(PermissionError):
            check_allowed(name)
    assert check_allowed('get_app_state') is None

def test_extract_error_never_silent():
    with pytest.raises(MunimError):
        extract_text({"isError":True,"content":[{"type":"text","text":"fail"}]})
    assert extract_text({"isError":False,"content":[{"type":"text","text":"ok"}]})=="ok"

def test_image_validator_rejects_remote_black_strip():
    output=io.BytesIO()
    Image.new("RGB",(1000,1),"black").save(output,"JPEG")
    with pytest.raises(MunimError):
        validate_capture(base64.b64encode(output.getvalue()).decode())

def test_image_validator_accepts_meaningful_frame():
    output=io.BytesIO()
    picture=Image.new("RGB",(100,80),"white")
    for x in range(50):
        for y in range(80):
            picture.putpixel((x,y),(10,20,80))
    picture.save(output,"JPEG")
    assert validate_capture(base64.b64encode(output.getvalue()).decode())["width"]==100

def test_new_munim_process_gets_new_response_queue(monkeypatch, tmp_path):
    import io
    from munim_rpc import MunimClient
    binary=tmp_path / "portable.exe"
    binary.touch()
    class FakePopen:
        stdin=io.StringIO()
        stdout=io.StringIO("")
        def poll(self): return 0
    monkeypatch.setattr("munim_rpc.subprocess.Popen",lambda *a,**kw: FakePopen())
    client=MunimClient(str(binary))
    old=client._responses
    old.put({"id":1,"result":{"stale":True}})
    monkeypatch.setattr(client,"_request",lambda *a,**kw: {})
    client._open()
    assert client._responses is not old
