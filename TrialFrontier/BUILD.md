# 런처 소스 빌드

공개 범위는 런처와 설치 도구입니다. 이 저장소만으로 게임 본체를 재컴파일할 수는 없습니다. ROM, EBOOT, 재컴파일된 게임 명령어, 원본 그래픽·음원, 디스크 키는 소스에 포함하지 않습니다.

## Windows 준비

Python 3.10 이상(x64, Tkinter 포함), PyInstaller, Pillow, PyCryptodome을 사용합니다.

```powershell
cd TrialFrontier
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

다음 파일은 릴리즈 ZIP에서 준비하거나 해당 도구의 공식 배포본을 사용합니다.

- `MacrossTrialFrontier.exe`: 이 프로젝트 릴리즈의 게임 본체
- `tools/rpcs3`: RPCS3와 해당 버전의 DLL 및 `qt6/plugins`
- `tools/texconv.exe`: DirectXTex texconv

```powershell
.venv\Scripts\python.exe build_launcher.py `
  --native-exe "D:\existing-release\MacrossTrialFrontier.exe" `
  --rpcs3-dir "D:\existing-release\tools\rpcs3" `
  --texconv "D:\existing-release\tools\texconv.exe"
```

결과는 `dist/TrialFrontier/TrialFrontier.exe`입니다. 빌드 도구는 이미 존재하는 출력 폴더를 덮어쓰지 않습니다. 재배포할 때는 동봉한 외부 도구에 해당하는 라이선스·고지·소스 제공 조건도 함께 충족해야 합니다. 원래 릴리즈의 `licenses`, `THIRD-PARTY.txt`, 해당 라이브러리 소스도 참고하세요.

## 코드 구성

| 파일 | 역할 |
| --- | --- |
| `launcher/launcher.py` | 최초 설치 UI, ISO·키 입력, 설치 파일 상태 확인, 게임 실행 |
| `launcher/install_core.py` | ISO 선택/마운트 해석, 섹터 읽기, EBOOT 준비, 임시 설치 후 반영, 무결성 기록 |
| `launcher/iso9660.py` | ISO9660 파일 목록 및 필요한 범위 추출 |
| `launcher/external_process.py` | PyInstaller의 DLL 경로와 외부 도구 실행 환경 분리 |
| `launcher/build_korean.py` | 로컬 ROM의 원문 복원, 한글 폰트 및 번역 적용 파일 생성 |
| `launcher/extract_trial.py` | PIDX/FSTS 아카이브와 텍스트 읽기 |
| `launcher/prepare_asset_cache.py` | 압축 해제 캐시 사전 생성 |
| `resources/korean.json` | 한글 번역 및 원본 파일 내 위치 정보. 원문은 사용자 파일에서 읽음 |

`build_korean.py`의 단독 실행 진입점에는 개발 시 사용한 폴더 배치가 남아 있습니다. 배포 런처는 그 경로를 사용하지 않고 `build()`에 설치 임시 폴더와 번역 경로를 전달합니다.

원본 버전을 전체 ROM 해시로 고정하지 않습니다. 다만 현재 게임 실행 구조와 번역 위치 정보는 Trial Frontier 기준이므로 임의의 버전 호환성을 보장하지 않습니다.

자동 업데이트는 공개 GitHub 릴리즈의 TrialFrontier 전체 ZIP과 asset SHA-256 digest를 사용합니다. diagnostics.py는 로컬 진단 ZIP만 작성합니다. updater.py와 asset_overlay.py를 함께 빌드해야 합니다.
