"""Local-only run reports. No telemetry, ROM, keys or saved games collected."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import zipfile

def prepare_performance_capture(root):
    """Fixed local paths: raw captures overwrite each run, no unbounded history."""
    folder=Path(root)/'diagnostics'/'performance-current'
    folder.mkdir(parents=True,exist_ok=True)
    for name in ('frames.bin','waits.bin'):
        (folder/name).unlink(missing_ok=True)
    return folder

def pack_performance_capture(root,folder,report,settings):
    base=Path(root)/'diagnostics'
    staging=base/'performance-latest.zip.tmp'
    latest=base/'performance-latest.zip'
    previous=base/'performance-previous.zip'
    with zipfile.ZipFile(staging,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.json',json.dumps(report,ensure_ascii=False,indent=2))
        if settings.exists():z.write(settings,'settings.ini')
        for name,limit in [('frames.bin',1296008),('waits.bin',4194312)]:
            path=folder/name
            if path.exists():
                with path.open('rb') as stream:z.writestr(name,stream.read(limit))
        log=Path(root)/'launcher.log'
        if log.exists():
            with log.open('rb') as stream:
                head=stream.read(65536)
                stream.seek(0,2);size=stream.tell()
                stream.seek(max(len(head),size-262144))
                z.writestr('launcher-excerpt.log',head+b'\n--- tail ---\n'+stream.read(262144))
    if latest.exists():os.replace(latest,previous)
    os.replace(staging,latest)

def run_and_record(root,version,launch):
    root=Path(root)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder=root/'diagnostics'/stamp;folder.mkdir(parents=True)
    report=dict(version=version,started=stamp,os=platform.platform(),
                machine=platform.machine(),processor=platform.processor(),logical_cpus=os.cpu_count())
    settings=root/'settings.ini'
    if settings.exists():shutil.copy2(settings,folder/'settings.ini')
    perf=prepare_performance_capture(root)
    names={'PS3RECOMP_VK_FRAME_TRACE':str(perf/'frames.bin'),
           'PS3RECOMP_VK_WAIT_TRACE':str(perf/'waits.bin')}
    original={key:os.environ.get(key) for key in names}
    os.environ.update(names)
    report['performance_capture']='Vulkan host wait attribution; not GPU timestamps; bounded raw files'
    try:
        process=launch(root);report['pid']=process.pid
        code=process.wait();report.update(exit_code=code,exit_hex=f'0x{code & 0xffffffff:08X}')
    except Exception as error:
        report['launch_error']=str(error)
        raise
    finally:
        for key,value in original.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        pack_performance_capture(root,perf,report,folder/'settings.ini')
        if (root/'launcher.log').exists():shutil.copy2(root/'launcher.log',folder/'launcher.log')
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with zipfile.ZipFile(folder.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for file in folder.iterdir():z.write(file,file.name)
