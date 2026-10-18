from events import EventBuffer

def test_duplicate_events_coalesced():
    b=EventBuffer(limit=3,quiet_ms=150)
    b.push(10,0x800E,123,clock_ms=100)
    b.push(10,0x800E,123,clock_ms=130)
    assert len(b.drain())==1

def test_bounded_events_and_drain():
    b=EventBuffer(limit=2,quiet_ms=0)
    for i in range(5): b.push(12,0x8000+i,i,clock_ms=100+i)
    assert len(b.drain())==2
    assert b.drain()==[]

def test_rejects_zeros_and_different_pids():
    b=EventBuffer(limit=5)
    b.push(0,0x800E,1,clock_ms=100)
    assert b.drain()==[]
