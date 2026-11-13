"""Portable first-run launcher. No per-user installation or stored disc keys."""
import ctypes
import os
from pathlib import Path
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

if not getattr(sys,'frozen',False):
    base=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(base),str(base/'localization')]
from install_core import install, ready, launch, resolve_source, inspect_iso, parse_key, KeyRequired, Cancelled, KEY_HELP
import updater

VERSION='0.1.6-test'
ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'installer-dev'
BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
RESOURCES={'rpcs3':ROOT/'tools/rpcs3/rpcs3.exe', 'texconv':ROOT/'tools/texconv.exe',
           'translations':ROOT/'resources/korean.json'}

def main():
    if len(sys.argv)==4 and sys.argv[1]=='--apply-update':
        updater.apply_pending(Path(sys.argv[2]),int(sys.argv[3]));return
    # A directory-scoped OS lock survives launcher renames and releases on exit.
    ROOT.mkdir(parents=True,exist_ok=True)
    lock=(ROOT/'.launcher.lock').open('a+b')
    import msvcrt
    lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        ctypes.windll.user32.MessageBoxW(None,'이미 이 폴더의 런처가 실행 중입니다.','Trial Frontier',0x40)
        return
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    window=tk.Tk();window.withdraw()
    window.title('Macross Trial Frontier — 테스트 버전 '+VERSION)
    try:window.iconbitmap(str(BUNDLE/'icon.ico'))
    except tk.TclError:pass
    window.deiconify();window.geometry('680x340');window.minsize(620,320)
    frame=ttk.Frame(window,padding=22);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='트라이얼 프론티어 · 최초 실행 준비',font=('맑은 고딕',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='거짓의 가희 Hybrid Pack (BLJS93001)의 ISO를 선택하세요.\n설치 파일·저장·설정은 이 폴더에 보관됩니다. 물리 BD는 지원하지 않습니다.',wraplength=610).pack(anchor='w',pady=(12,16))
    source=tk.StringVar();ttk.Entry(frame,textvariable=source).pack(fill='x')
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=8)
    def pick_file():
        value=filedialog.askopenfilename(parent=window,title='ISO 선택',filetypes=[('ISO 이미지','*.iso')])
        if value:source.set(value)
    def pick_mount():
        value=filedialog.askdirectory(parent=window,title='마운트된 ISO의 드라이브 선택')
        if value:source.set(value)
    file_button=ttk.Button(buttons,text='ISO 파일 선택',command=pick_file);file_button.pack(side='left')
    mount_button=ttk.Button(buttons,text='마운트된 ISO 선택',command=pick_mount);mount_button.pack(side='left',padx=8)
    ttk.Button(buttons,text='디스크 키 안내',command=lambda:webbrowser.open(KEY_HELP)).pack(side='right')
    status=tk.StringVar(value='암호화된 ISO일 때만 사용자가 준비한 디스크 키를 요청합니다.')
    ttk.Label(frame,textvariable=status,wraplength=610).pack(anchor='w',pady=(10,4))
    bar=ttk.Progressbar(frame,maximum=100);bar.pack(fill='x')
    events=queue.Queue();cancel=threading.Event();state={'busy':False,'key':None,'source':None}
    controls=ttk.Frame(frame);controls.pack(fill='x',pady=12)
    def enable(value):
        for button in (file_button,mount_button,start):button.config(state='normal' if value else 'disabled')
    def progress(text,percent):events.put(('progress',(text,percent)))
    def run_game():
        from diagnostics import run_and_record
        run_and_record(ROOT,VERSION,launch)
    def startup():
        if getattr(sys,'frozen',False) and '--skip-update-once' not in sys.argv:
            try:
                release=updater.latest(VERSION)
                if release:
                    payload=updater.download(ROOT,release,progress)
                    events.put(('update',payload));return
            except Exception as error:
                (ROOT/'update.log').write_text(str(error),encoding='utf-8')
        valid=ready(ROOT)
        if valid:
            try:
                from install_core import refresh_translation
                refresh_translation(ROOT,RESOURCES,progress)
            except Exception as error:
                events.put(('error',error));return
        events.put(('ready',valid))
    def worker(path,key):
        try:
            iso=resolve_source(path);inspect_iso(iso,key)
            install(iso,ROOT,RESOURCES,key,progress,cancel)
            events.put(('done',None))
        except KeyRequired:events.put(('key',None))
        except Cancelled as error:events.put(('cancel',str(error)))
        except Exception as error:events.put(('error',str(error) or type(error).__name__))
    def begin(key=None):
        if not source.get().strip():pick_file()
        if not source.get().strip():return
        state['busy']=True;enable(False);cancel.clear();bar['value']=0
        status.set('ISO 확인 중…');threading.Thread(target=worker,args=(source.get().strip(),key),daemon=True).start()
    def close():
        if state['busy']:
            cancel.set();status.set('현재 준비 단계가 끝나면 취소합니다. 잠시 기다려 주세요.')
        else:window.destroy()
    start=ttk.Button(controls,text='설치 후 게임 실행',command=begin);start.pack(side='right')
    ttk.Button(controls,text='취소 / 닫기',command=close).pack(side='right',padx=8)
    window.protocol('WM_DELETE_WINDOW',close)
    def poll():
        try:
            while True:
                kind,data=events.get_nowait()
                if kind=='progress':status.set(data[0]);bar['value']=data[1];continue
                state['busy']=False;enable(True)
                if kind=='update':
                    updater.handoff(ROOT,data);window.destroy();return
                elif kind=='ready':
                    bar.stop();bar.config(mode='determinate');bar['value']=0
                    if data:
                        window.withdraw()
                        try:run_game()
                        except Exception as error:messagebox.showerror('실행 실패',str(error),parent=window)
                        window.destroy();return
                    status.set('설치 파일이 없거나 손상되었습니다. ISO를 선택해 설치하세요. 저장·설정은 유지됩니다.')
                elif kind=='key':
                    if cancel.is_set():status.set('취소했습니다.');continue
                    value=simpledialog.askstring('디스크 키','ISO에 맞는 32자리 디스크 키를 입력하세요.\n키는 파일에 저장하지 않습니다.',show='*',parent=window)
                    if value is not None:
                        try:key=parse_key(value)
                        except ValueError as error:messagebox.showerror('키 형식 오류',str(error),parent=window)
                        else:begin(key)
                    else:status.set('키 입력을 취소했습니다.')
                elif kind=='done':
                    window.withdraw()
                    try:run_game()
                    except Exception as error:messagebox.showerror('실행 실패',str(error),parent=window)
                    window.destroy();return
                elif kind=='error':status.set('준비에 실패했습니다. 원인을 확인한 뒤 다시 시도하세요.');messagebox.showerror('설치 실패',data,parent=window)
                else:status.set(data)
        except queue.Empty:pass
        window.after(100,poll)
    candidates=list(ROOT.glob('*.iso'))+list((ROOT/'iso').glob('*.iso'))
    if len(candidates)==1:source.set(str(candidates[0]))
    enable(False);status.set('새 버전 및 설치 파일 확인 중…');bar.config(mode='indeterminate');bar.start()
    threading.Thread(target=startup,daemon=True).start()
    poll();window.mainloop()

if __name__=='__main__':
    try:main()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None,str(error),'Trial Frontier 런처 오류',0x10)
