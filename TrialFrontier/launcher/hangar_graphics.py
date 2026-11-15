"""Hangar texture recipes; these contain no original game artwork."""

import io, json, subprocess

from pathlib import Path

from graphics_process import encode
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT=Path(__file__).resolve().parents[2]

def replace_label(im, box, text, size=15, color=(255,255,255)):
    x,y,r,b = box
    # Render at higher resolution then reduce for smooth small UI lettering.
    scale=4
    layer=Image.new('RGBA',((r-x)*scale,(b-y)*scale))
    font=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',size*scale)
    draw=ImageDraw.Draw(layer)
    while draw.textbbox((0,0),text,font=font)[2] > (r-x-2)*scale:
        size-=1
        if size<8: raise ValueError('Label does not fit: '+text)
        font=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',size*scale)
    bounds=draw.textbbox((0,0),text,font=font)
    top=((b-y)*scale-(bounds[3]-bounds[1]))//2-bounds[1]
    draw.text((scale,top),text,font=font,fill=(*color,255))
    layer=layer.resize((r-x,b-y),Image.Resampling.LANCZOS)
    glow=layer.filter(ImageFilter.GaussianBlur(.6))
    glow.alpha_composite(layer)
    im.paste((0,0,0,0),box)
    im.alpha_composite(glow,(x,y))

def graphics(pack, out, texconv=None):
    out.mkdir(parents=True,exist_ok=True)
    entries={str(path):row for _,path,row in pack.bundled_entries('hangar')}
    specs={
      'data/menu/hangar/hangar_subwindow_menu.dds': [
        ((1,110,80,132),'사격 방어'),((1,132,80,153),'격투 방어'),
        ((1,153,80,174),'속도'),((1,174,80,195),'부스트'),
        ((1,195,80,216),'밸런서'),((1,216,80,237),'선회'),
        ((1,237,84,258),'레이더 성능'),
        ((89,153,142,174),'체  력'),((89,174,142,195),'사  격'),
        ((89,195,142,216),'격  투'),((89,216,142,237),'방  어'),
        ((89,237,142,258),'속  도'),
        ((164,110,237,132),'제한 시간:'),((164,153,222,174),'집  중'),
        ((164,174,222,195),'각  성'),((164,195,222,216),'날씨:'),
        ((164,216,222,237),'시각:'),((164,237,222,258),'목적:'),
      ],
      'data/menu/hangar/hanger_guide.dds': [
        *[((72,y,101,y+19),'선택') for y in (31,59,87)],
        *[((129,y,157,y+19),'결정') for y in (31,59,87)],
        ((303,59,411,78),'숨겨진 미션 전환'),((303,87,411,106),'일반 미션 전환'),
        ((50,115,114,135),'기체 보기'),((147,115,265,135),'미션 선택으로'),((322,115,404,135),'조작 설명서'),
        ((50,143,91,165),'결정'),((118,143,180,164),'기체 보기'),((207,143,324,164),'미션 선택으로'),((381,143,460,164),'조작 설명서'),
        ((72,172,101,192),'선택'),((129,172,192,192),'기체 보기'),((221,172,339,192),'미션 선택으로'),((395,172,478,192),'조작 설명서'),
      ],
    }
    replacements={};audit=[]
    for path,labels in specs.items():
        original_dds=pack.read(entries[path])
        original=Image.open(io.BytesIO(original_dds)).convert('RGBA')
        im=original.copy();mask=Image.new('1',im.size);md=ImageDraw.Draw(mask)
        for box,text in labels:
            guide=path.endswith('hanger_guide.dds')
            color=(255,172,172) if guide and box==(50,143,91,165) else (117,242,255) if guide else (255,255,255)
            replace_label(im,box,text,12 if guide else 15,color)
            md.rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=1)
        for a,b,m in zip(original.getdata(),im.getdata(),mask.getdata()):
            if not m and a!=b:raise AssertionError('Pixel outside text regions changed')
        dest=out/Path(path).name
        im.save(dest.with_suffix('.png'))
        dest.write_bytes(encode(original_dds,im))
        replacements[path]=dest.read_bytes()
        bg=Image.new('RGBA',im.size,(15,30,55,255));bg.alpha_composite(im)
        bg.resize((im.width*3,im.height*3)).save(dest.with_suffix('.preview.png'))
        audit.append(dict(path=path,labels=[dict(box=box,korean=text) for box,text in labels],outside_pixels_unchanged=True))
    (out/'graphics-manifest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    return replacements
