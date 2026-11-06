"""Keep frozen Python's DLL search path out of native child processes."""
from contextlib import contextmanager
import os
import sys

@contextmanager
def native_dll_search():
    if sys.platform!='win32' or not getattr(sys,'frozen',False):
        yield
        return
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDllDirectoryW.argtypes=[ctypes.c_uint32,ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    saved=ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(saved),saved)
    if not kernel.SetDllDirectoryW(None):raise ctypes.WinError(ctypes.get_last_error())
    try:yield
    finally:
        if not kernel.SetDllDirectoryW(saved.value or None):raise ctypes.WinError(ctypes.get_last_error())

def native_environment():
    env=os.environ.copy()
    bundle=getattr(sys,'_MEIPASS',None)
    if bundle:
        base=os.path.normcase(os.path.abspath(bundle))
        env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep)
                                   if not os.path.normcase(os.path.abspath(p)).startswith(base+os.sep)
                                   and os.path.normcase(os.path.abspath(p))!=base)
    return env
