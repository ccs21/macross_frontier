"""Korean UI artwork, kept out of the runtime text dictionary.

All rectangles use original texture coordinates. Icons, UVs, image dimensions,
and pixels outside the recorded text regions remain unchanged in the encoded DDS.
"""
import io
import json
import subprocess
from pathlib import Path
from graphics_process import encode
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT=Path(__file__).resolve().parents[2]
CATALOG = [{'id': 'GFX-050', 'path': 'data/loading/wallpaper00.dds'}, {'id': 'GFX-051', 'path': 'data/loading/wallpaper01.dds'}, {'id': 'GFX-052', 'path': 'data/logo/attention.dds'}, {'id': 'GFX-064', 'path': 'data/menu/dialog/dialog_text.dds'}, {'id': 'GFX-065', 'path': 'data/menu/dialog/mission_pose.dds'}, {'id': 'GFX-067', 'path': 'data/menu/dialog/ura_command.dds'}, {'id': 'GFX-068', 'path': 'data/menu/dialog/wallpaper_manual.dds'}, {'id': 'GFX-073', 'path': 'data/menu/hangar/hngr_face_dont.dds'}, {'id': 'GFX-092', 'path': 'data/menu/viewer/viewer_guide.dds'}, {'id': 'GFX-096', 'path': 'data/script/fesrat/ope29.dds'}, {'id': 'GFX-098', 'path': 'data/script/fesrat/ope_w207.dds'}, {'id': 'GFX-123', 'path': 'data/script/fesrat_m/mf_000_title.dds', 'translation': '라이브 파이어 매뉴버스'}, {'id': 'GFX-124', 'path': 'data/script/fesrat_m/mf_001_title.dds', 'translation': '유니버설 버니'}, {'id': 'GFX-125', 'path': 'data/script/fesrat_m/mf_002_title.dds', 'translation': '토네이도'}, {'id': 'GFX-126', 'path': 'data/script/fesrat_m/mf_003_title.dds', 'translation': '웨이브스 오브 바쥬라'}, {'id': 'GFX-127', 'path': 'data/script/fesrat_m/mf_004_title.dds', 'translation': '스컬 스쿼드론'}, {'id': 'GFX-128', 'path': 'data/script/fesrat_m/mf_005_title.dds', 'translation': '리멤버 쿼드런'}]

BASE = [
('방향키·왼쪽 스틱','기체 조작'),
('방향키·왼쪽 스틱 ↑↑','앞 스텝 (파이터: 전방 롤링, 최대 3회)'),
('방향키·왼쪽 스틱 ↓↓','뒤 스텝 (파이터: 역분사)'),
('방향키·왼쪽 스틱 ←←','왼쪽 스텝 (파이터: 왼쪽 롤링, 최대 3회)'),
('방향키·왼쪽 스틱 →→','오른쪽 스텝 (파이터: 오른쪽 롤링, 최대 3회)'),
('R1 버튼','록온/록온 대상 전환'),('L1 + R1 버튼','록온 해제'),
('R1 길게 누르기','록온 대상 쪽으로 향함 (파이터)'),
('L1 버튼','가드·시점 초기화 (가워크: 호버링)'),
('○ 버튼','특수 무장 공격'),('□ 버튼','주 무장 공격'),
('△ 버튼','격투 공격 (파이터: 브레이크)'),
('× 버튼','상승 부스트 (파이터: 가속 부스트)'),
('×× 버튼','하강 부스트 (파이터: 가속 부스트)'),
('오른쪽 스틱','변신'),('L2 버튼','왼쪽 요잉 (파이터)'),('R2 버튼','오른쪽 요잉 (파이터)')]
ADV = [
('△ 연타','연속 격투 (배틀로이드·가워크)'),
('방향키 ↑ + △','올려치기 (배틀로이드)'),
('대시 중 △','대시 격투 (배틀로이드·가워크)'),
('△를 잠시 누른 뒤 놓기','모으기 격투 (배틀로이드·가워크)'),
('□ + ×','안티 미사일 액션'),('L1 + ○','차지 사격'),
('L1 + △','차지 격투 (배틀로이드·가워크)'),
('△ + ○','SP 어택 / SP 3칸 소비'),('L1 + □','특수 무장 전환'),
('○ + ×','커맨드 스킬 / SP 1~3칸 소비'),('L3 + R3','추가 장비 분리'),
('L1 + 방향키 ↑↑','상승 대시 (배틀로이드·가워크)'),
('L1 + 방향키 ↓↓','하강 대시 (배틀로이드·가워크)'),
('L1 + ×','차지 부스트'),('다운 공격에 맞은 직후 ×','다운 회피'),
('다운 상태에서 × 연타','다운 회복')]
REAL=[('R1 + 방향키 ↑','에이스 우선 록온'),('R1 + 방향키 ↓','졸개 우선 록온'),
('SELECT 버튼','카메라를 노멀 플라이트 시점으로 전환'),
('R1 길게 누르기','카메라를 노멀 플라이트 시점으로 전환'),
('L2 + R2','기체 자세를 수평으로 초기화')]

def render(im,box,text,size=18,color=(255,255,255),background='transparent',center=False,shadow=False):
    x,y,r,b=map(int,box);w,h=r-x,b-y
    if background=='sample':
        # Each row samples its clean left margin; panel borders are excluded.
        clean=Image.new('RGBA',(w,h))
        for yy in range(h):
            c=im.getpixel((x,y+yy))
            ImageDraw.Draw(clean).line((0,yy,w,yy),fill=c)
        im.paste(clean,(x,y))
    elif isinstance(background,tuple):im.paste(background,(x,y,r,b))
    else:im.paste((0,0,0,0),(x,y,r,b))
    layer=Image.new('RGBA',(w*4,h*4));d=ImageDraw.Draw(layer)
    while True:
        font=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',round(size*4))
        bounds=d.textbbox((0,0),text,font=font)
        if bounds[2]-bounds[0]<=(w-2)*4 and bounds[3]-bounds[1]<=(h-2)*4:break
        size-=.25
        if size<6:raise ValueError('Cannot fit '+text)
    px=((w*4-bounds[2])//2 if center else 4)
    py=(h*4-bounds[3]+bounds[1])//2-bounds[1]
    if shadow:d.text((px+5,py+6),text,font=font,fill=(0,0,0,230),stroke_width=3,stroke_fill=(0,0,0,230))
    d.text((px,py),text,font=font,fill=(*color,255))
    im.alpha_composite(layer.resize((w,h),Image.Resampling.LANCZOS),(x,y))

def build(pack,out,texconv=None):
    out.mkdir(parents=True,exist_ok=True)
    catalog=CATALOG
    entries={str(p):r for _,p,r in pack.bundled_entries()}
    entries.update({str(p):r for _,p,r in pack.entries()})
    from hangar_graphics import graphics
    replacements=graphics(pack,out,texconv);audits=[]
    for rec in catalog:
        n=int(rec['id'][4:])
        if n not in {50,51,52,64,65,67,68,73,92,96,98,123,124,125,126,127,128}:continue
        path=rec['path'];original_dds=pack.read(entries[path]);original=Image.open(io.BytesIO(original_dds)).convert('RGBA');im=original.copy();ops=[]
        def put(box,text,**kw):
            box=tuple(map(int,box));render(im,box,text,**kw);ops.append(dict(box=box,korean=text))
        def table(x,y,split,right,rows,step=20):
            for i,(a,b) in enumerate(rows):
                color=(255,255,0) if ('SP ' in b or '공격' in b or b=='변신' or i==0 and rows==BASE) else (255,255,255)
                put((x+3,y+i*step+2,split-2,y+(i+1)*step-2),a,size=18,background='sample',color=color)
                star=(rows==ADV and i in (5,6,13)) or (rows==REAL and i in (2,3,4))
                put((split+3,y+i*step+2,right-(28 if star else 3),y+(i+1)*step-2),b,size=18,background='sample',color=color)
        def diagram(x,y,red=False,sticks=True):
            # The original blue/red label cells are 100 x 22 pixels.
            col=(140,12,18,255) if red else (8,109,165,255)
            for xx,yy,t in [(0,0,'L2 버튼'),(0,34,'L1 버튼'),(0,71,'START 버튼'),(0,104,'SELECT 버튼'),(0,142,'방향키'),(0,209,'왼쪽 스틱'),(440,0,'R2 버튼'),(440,34,'R1 버튼'),(440,71,'□ 버튼'),(440,104,'△ 버튼'),(440,142,'○ 버튼'),(440,175,'× 버튼'),(440,209,'오른쪽 스틱')]:
                preserve_icon=t in ('L2 버튼','L1 버튼','R2 버튼','R1 버튼','□ 버튼','△ 버튼','○ 버튼','× 버튼')
                cut=40 if t in ('□ 버튼','△ 버튼','○ 버튼','× 버튼') else 44
                put((x+xx+(cut if preserve_icon else 4),y+yy,x+xx+99,y+yy+23),'버튼' if preserve_icon else t,size=16,background=col,center=True)
            if sticks:
                for xx,t in [(0,'L3 버튼'),(440,'R3 버튼')]:put((x+xx+44,y+235,x+xx+99,y+258),'버튼',size=16,background=col,center=True)
        if n in (50,65):
            diagram(639,53,sticks=False)
            table(646,298,840,1174,BASE)
            if n==65:
                table(108,418,302,634,REAL)
                put((535,520,634,537),'★ 리얼 플라이트',size=13,background='sample')
                small=[ADV[4],ADV[5],ADV[6],ADV[7],ADV[9]]
                table(108,538,302,634,small)
                put((479,639,634,656),'★ SP 1칸 소비',size=13,background='sample')
        elif n==51:
            diagram(98,56,red=True)
            table(108,328,348,634,ADV)
            put((476,650,634,669),'★ SP 1칸 소비',size=13,background='sample')
        elif n==68:
            diagram(98,56)
            put((954,152,1180,192),'조작 설명서',size=36,background='sample')
            table(108,322,302,630,BASE)
            table(652,322,890,1175,ADV)
            table(652,196,845,1175,REAL)
            put((1080,299,1175,315),'★ 리얼 플라이트',size=12,background='sample')
            put((1016,642,1175,660),'★ SP 1칸 소비',size=14,background='sample')
        elif n==64:
            for i,t in enumerate(['미션 선택으로','미션 재도전','미션 재개','시점 변경','2D 표시 전환','미션 중단']):put((16,9+28*i,149,30+28*i),t,size=16,center=True)
            put((16,229,150,250),'미션 BGM',size=16,center=True)
        elif n==67:
            for box,t in [((35,10,131,36),'L1 버튼'),((195,10,290,36),'R2 버튼'),((349,10,446,36),'START 버튼')]:put(box,t,size=19,background=(150,8,10,255),center=True)
        elif n==73:
            put((28,113,162,150),'출격 불가',size=29,background='sample')
            put((202,54,269,74),'출격 불가',size=14,background='sample')
        elif n==52:
            put((13,208,797,254),'저장 데이터는 포터블 게임 폴더에 보관됩니다.',size=28,background=(15,22,31,245),center=True,shadow=True)
        elif n==92:
            # Retain controller symbols. Replace both caption and faint reflection.
            for box,t in [((183,36,257,64),'카메라 이동'),((365,36,441,64),'기체 회전'),((519,36,557,64),'하강'),((628,36,665,64),'상승'),((715,36,752,64),'변신'),((804,36,1010,64),'카메라·기체 회전 초기화'),((1070,28,1130,48),'돌아가기'),((1070,49,1210,72),'메뉴 켜기/끄기')]:
                put(box,t,size=14,color=(210,220,230))
                x,y,r,b=box
                if b<=64:
                    reflected=im.crop(box).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    alpha=reflected.getchannel('A').point(lambda a:int(a*.16));reflected.putalpha(alpha)
                    rb=(x,b,r,min(im.height,b+b-y));im.paste((0,0,0,0),rb);im.alpha_composite(reflected,(x,b));ops.append(dict(box=rb,korean='reflection'))
        elif n==96:
            texts=['공격 목표 출현','공격 목표 확인','아군기 도착','아군기 확인','적 출현','적 확인','적 에이스 출현','적 에이스 확인','작전 시간 초과','공격 목표 격파','적 전멸','적 철수','테스트 완료']
            widths=[190,190,160,160,100,132,181,181,190,190,100,100,150]
            for i,(t,w) in enumerate(zip(texts,widths)):put((1,5+i*30,w,35+i*30),t,size=24)
        elif n==98:
            for box,t in [((395,20,434,40),'남은'),((477,20,501,40),'분'),((395,61,434,80),'남은'),((477,61,501,80),'초'),((28,66,151,86),'적 출현'),((24,108,153,130),'적 에이스 출현'),((193,108,327,130),'공격 목표 출현'),((368,108,503,130),'아군기 도착'),((26,151,160,173),'아군기 대파')]:put(box,t,size=16,center=True,shadow=True)
        elif n>=123:
            put((0,60,im.width,127),rec['translation'],size=44,shadow=True)
        # Check pixels outside our recorded text regions in the encoded DDS.
        mask=Image.new('1',im.size);md=ImageDraw.Draw(mask)
        for op in ops:
            x,y,r,b=op['box'];md.rectangle((x,y,r-1,b-1),fill=1)
        assert all(m or a==b for a,b,m in zip(original.getdata(),im.getdata(),mask.getdata())),path
        dest=out/Path(path).name;im.save(dest.with_suffix('.png'))
        dest.write_bytes(encode(original_dds,im))
        replacements[path]=dest.read_bytes()
        bg=Image.new('RGBA',im.size,(25,35,45,255));bg.alpha_composite(im);bg.save(dest.with_suffix('.preview.png'))
        audits.append(dict(id=rec['id'],path=path,operations=ops,outside_pixels_unchanged=True))
    (out/'full-graphics-manifest.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
    return replacements
