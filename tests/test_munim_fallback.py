import pytest
from munim_rpc import MunimClient, MunimError

def test_retries_on_empty_semantics_with_bounded_depth():
    client=MunimClient("not_launched")
    calls=[]
    def fake(tool,args):
        calls.append(dict(args))
        if args["max_depth"]==3:
            return {"content":[{"type":"text","text":"window 0\nno interactive elements found - use screenshot"}]}
        return {"content":[{"type":"text","text":"window 0\n[1] Button New tab"}]}
    client.tool=fake
    assert "Button" in client.text("1234")
    assert [a["max_depth"] for a in calls]==[3,8]
    assert all(a["ocr"]=="never" for a in calls)

def test_does_not_rescan_accessible_fixture():
    client=MunimClient("not_launched")
    calls=[]
    def fake(name,args):
        calls.append(args)
        return {"content":[{"type":"text","text":"Window\n[1] Edit LAB-INITIAL"}]}
    client.tool=fake
    assert "Edit" in client.text("1234")
    assert len(calls)==1

def test_unavailable_semantics_fail_closed_after_bounded_retry():
    client=MunimClient("not_launched")
    calls=[]
    def fake(name,args):
        calls.append(dict(args))
        return {"content":[{"type":"text","text":"Window\nno interactive elements found - use screenshot"}]}
    client.tool=fake
    with pytest.raises(MunimError,match="semantic controls unavailable"):
        client.text("1234")
    assert [c["max_depth"] for c in calls]==[3,8]
