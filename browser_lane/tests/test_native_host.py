import io,json,struct
import pytest
from browser_lane.native_host import frame_message, read_message, normalize_job

def test_native_messages_use_little_endian_framing():
    data=frame_message({"type":"ping","id":"aaa"})
    assert int.from_bytes(data[:4],"little")==len(data)-4
    assert read_message(io.BytesIO(data))=={"type":"ping","id":"aaa"}

def test_native_messaging_rejects_overlarge_frame():
    with pytest.raises(ValueError):
        read_message(io.BytesIO(struct.pack("<I",2_000_000)))

def test_native_job_is_limited_to_known_operation_and_fresh_timestamp():
    job={"id":"a"*32,"op":"open","url":"https://example.com","created":100}
    assert normalize_job(job,now=100)["op"]=="open"
    for bad in [
        dict(job,op="shell"),dict(job,url="file:///x"),
        dict(job,created=1),dict(job,id="../escape")
    ]:
        with pytest.raises(ValueError):
            normalize_job(bad,now=100)
