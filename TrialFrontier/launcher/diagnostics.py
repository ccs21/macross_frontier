"""Local-only run reports. No telemetry, ROM, keys or saved games collected."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import zipfile

def run_and_record(root,version,launch):
    root=Path(root)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder=root/'diagnostics'/stamp;folder.mkdir(parents=True)
    report=dict(version=version,started=stamp,os=platform.platform(),
                machine=platform.machine(),processor=platform.processor(),logical_cpus=os.cpu_count())
    settings=root/'settings.ini'
    if settings.exists():shutil.copy2(settings,folder/'settings.ini')
    try:
        process=launch(root);report['pid']=process.pid
        code=process.wait();report.update(exit_code=code,exit_hex=f'0x{code & 0xffffffff:08X}')
    except Exception as error:
        report['launch_error']=str(error)
        raise
    finally:
        if (root/'launcher.log').exists():shutil.copy2(root/'launcher.log',folder/'launcher.log')
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with zipfile.ZipFile(folder.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for file in folder.iterdir():z.write(file,file.name)
