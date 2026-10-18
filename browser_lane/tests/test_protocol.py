import pytest
from browser_lane.protocol import normalize_url, validate_selector, validate_value, validate_target_id

@pytest.mark.parametrize("url",[
    "chrome://settings","file:///C:/private.txt","javascript:alert(1)",
    "data:text/html,test","about:blank","ftp://example.com","https://x.test/#x\nInjected"
])
def test_disallowed_navigation(url):
    with pytest.raises(ValueError):
        normalize_url(url)

@pytest.mark.parametrize("url",["https://example.com/","http://example.org/a?q=hello","http://127.0.0.1:8001/fixture"])
def test_regular_web_urls_allowed(url):
    assert normalize_url(url)==url

@pytest.mark.parametrize("selector",["", " " * 2, "a\nbody", "#x\x00", "a"*1001])
def test_unsafe_selector_rejected(selector):
    with pytest.raises(ValueError):
        validate_selector(selector)

def test_selector_value_and_target_limits():
    assert validate_selector("input#query")=="input#query"
    assert validate_value("word")=="word"
    with pytest.raises(ValueError):validate_value("a"*10001)
    with pytest.raises(ValueError):validate_target_id("../history")
    assert validate_target_id("C6039F3DA")=="C6039F3DA"
