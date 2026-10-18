import pytest
from native_win32_state import decode_native_state

@pytest.mark.parametrize("style,flag,expected",[
    (2,0,("CheckBox","unchecked")),(3,1,("CheckBox","checked")),
    (5,2,("CheckBox","mixed")),(4,1,("RadioButton","selected")),
    (9,0,("RadioButton","unselected"))
])
def test_win32_buttons_read_only_states(style,flag,expected):
    row=decode_native_state("Button",style,flag,"LAB")
    assert row=={"kind":expected[0],"name":"LAB","state":expected[1]}

@pytest.mark.parametrize("value,state",[(0,"collapsed"),(1,"expanded")])
def test_win32_combo_read_only(value,state):
    assert decode_native_state("ComboBox",3,value,"")=={
      "kind":"ComboBox","name":"","state":state}

def test_unsupported_native_controls_never_invent_state():
    for cls,style,raw in [("Button",0,1),("Edit",0,1),("CustomControl",3,1),
                          ("Button",3,123),("ComboBox",3,7)]:
        assert decode_native_state(cls,style,raw,"LAB") is None
