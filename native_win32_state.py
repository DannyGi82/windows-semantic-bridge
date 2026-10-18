"""Read-only Win32 native check state sampler; no input/focus/UI changes.

Uses SendMessageTimeout (not SendMessage) on known native Button/ComboBox
classes. Any unsupported or hung control is left for the UIA fallback.
"""
import ctypes
from ctypes import wintypes

_TYPES_CHECK=frozenset((2,3,5,6))
_TYPES_RADIO=frozenset((4,9))

def decode_native_state(class_name:str,style:int,raw:int,name:str):
    if class_name.casefold()=="button":
        kind=style&0xF
        if kind in _TYPES_CHECK:
            state={0:"unchecked",1:"checked",2:"mixed"}.get(raw)
            return {"kind":"CheckBox","name":name,"state":state} if state else None
        if kind in _TYPES_RADIO:
            state={0:"unselected",1:"selected"}.get(raw)
            return {"kind":"RadioButton","name":name,"state":state} if state else None
    if class_name.casefold()=="combobox":
        state={0:"collapsed",1:"expanded"}.get(raw)
        return {"kind":"ComboBox","name":name,"state":state} if state else None
    return None


def read_native_hwnd(hwnd):
    user=ctypes.WinDLL("user32",use_last_error=True)
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetClassNameW.restype=ctypes.c_int
    class_name=ctypes.create_unicode_buffer(128)
    if not user.GetClassNameW(hwnd,class_name,128):
        return None
    cls=class_name.value.casefold()
    if cls not in ("button","combobox"):
        return None
    user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int]
    user.GetWindowLongW.restype=ctypes.c_long
    style=user.GetWindowLongW(hwnd,-16)
    if cls=="button" and (style&0xF) not in _TYPES_CHECK|_TYPES_RADIO:
        return None
    user.SendMessageTimeoutW.argtypes=[
        wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,
        wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=ctypes.c_size_t
    result=ctypes.c_size_t()
    message=0xF0 if cls=="button" else 0x157
    if not user.SendMessageTimeoutW(hwnd,message,0,0,0x0002,100,ctypes.byref(result)):
        return None
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetWindowTextW.restype=ctypes.c_int
    title=ctypes.create_unicode_buffer(241)
    user.GetWindowTextW(hwnd,title,241)
    return decode_native_state(cls,style,result.value,title.value)
