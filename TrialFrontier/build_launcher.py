"""Build the public launcher, then assemble with user-supplied runtime tools."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-exe',type=Path,required=True)
    parser.add_argument('--rpcs3-dir',type=Path,required=True)
    parser.add_argument('--texconv',type=Path,required=True)
    parser.add_argument('--spu-toolchain',type=Path,required=True,
                        help='Complete resources/spu-build from the full package (compiler included)')
    parser.add_argument('--native-runtime',type=Path,required=True,
                        help='Directory with SDL2.dll, llvmlite.dll and its companion DLL')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/TrialFrontier')
    args=parser.parse_args()
    for path in [args.native_exe,args.rpcs3_dir/'rpcs3.exe',args.texconv]:
        if not path.is_file():parser.error('Required file missing: '+str(path))
    for path in [args.spu_toolchain/'compiler/clang-cl.exe',args.spu_toolchain/'recipes.json',
                 args.native_runtime/'SDL2.dll',args.native_runtime/'llvmlite.dll']:
        if not path.is_file():parser.error('Required runtime input missing: '+str(path))
    output=args.output.resolve()
    if output.exists():parser.error('Output must be new; an installed game folder must never be overwritten.')
    work=ROOT/'build'
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','TrialFrontier','--icon',str(ROOT/'resources/icon.ico'),
        '--add-data',str(ROOT/'resources/icon.ico')+';.', '--paths',str(ROOT/'launcher'),
        '--hidden-import','Crypto.Cipher.AES','--hidden-import','build_korean',
        '--hidden-import','prepare_asset_cache','--hidden-import','extract_trial','--hidden-import','dataclasses',
        '--distpath',str(work/'dist'),'--workpath',str(work/'work'),'--specpath',str(work),
        str(ROOT/'launcher/launcher.py')],check=True)
    shutil.copytree(work/'dist/TrialFrontier',output)
    shutil.copy2(args.native_exe,output/'MacrossTrialFrontier.exe')
    tools=output/'tools';(tools/'rpcs3').mkdir(parents=True)
    for path in [args.rpcs3_dir/'rpcs3.exe',*args.rpcs3_dir.glob('*.dll')]:
        shutil.copy2(path,tools/'rpcs3'/path.name)
    shutil.copytree(args.rpcs3_dir/'qt6/plugins',tools/'rpcs3/qt6/plugins')
    shutil.copy2(args.texconv,tools/'texconv.exe')
    (output/'resources').mkdir();shutil.copy2(ROOT/'resources/korean.json',output/'resources/korean.json')
    shutil.copytree(args.spu_toolchain,output/'resources/spu-build')
    # Use the current authored recipes, tools and ABI headers.
    shutil.copytree(ROOT/'resources/spu-build',output/'resources/spu-build',dirs_exist_ok=True)
    shutil.copytree(args.native_runtime,output/'resources/native-runtime')
    for path in args.native_runtime.glob('*.dll'):shutil.copy2(path,output/path.name)
    (output/'iso').mkdir()
    for name in ['README.md','STATUS.md']:shutil.copy2(ROOT/name,output/name)
    print('Built launcher folder: '+str(output))
    print('For redistribution, include the corresponding third-party notices/licenses/source obligations.')

if __name__=='__main__':main()
