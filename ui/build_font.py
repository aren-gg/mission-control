"""Rebuild assets/pixel-font.ttf from sprites.GLYPHS without external font tools."""
import ast
from pathlib import Path
import struct

def build():
    root=Path(__file__).resolve().parents[1]
    module=ast.parse((root/'sprites.py').read_text())
    expression=next(n.value for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GLYPHS' for t in n.targets))
    glyphs=eval(compile(ast.Expression(expression),'<glyphs>','eval'),{'__builtins__':{}})
    pack=lambda fmt,*v:struct.pack('>'+fmt,*v)
    fontglyphs=[[]]
    for code in range(32,127):
        contours=[]
        for y,row in enumerate(glyphs[chr(code).upper()]):
            for x,v in enumerate(row):
                if v=='1':
                    a=x*100;b=(6-y)*100;contours.append([(a,b),(a,b+100),(a+100,b+100),(a+100,b)])
        fontglyphs.append(contours)
    glyf=b'';locations=[]
    for contours in fontglyphs:
        locations.append(len(glyf))
        if not contours:continue
        points=[p for rect in contours for p in rect];xs=[p[0] for p in points];ys=[p[1] for p in points]
        data=pack('hhhhh',len(contours),min(xs),min(ys),max(xs),max(ys))+b''.join(pack('H',i*4+3) for i in range(len(contours)))+pack('H',0)+bytes([1])*len(points)
        last=0
        for x,y in points:data+=pack('h',x-last);last=x
        last=0
        for x,y in points:data+=pack('h',y-last);last=y
        glyf+=data+b'\0'*((-len(data))%4)
    locations.append(len(glyf));n=len(fontglyphs)
    head=pack('IIIIHH',0x10000,0x10000,0,0x5f0f3cf5,3,1000)+pack('QQhhhhHHhhh',0,0,0,0,600,700,0,8,2,1,0)
    hhea=pack('IhhhHhhhhhhhhhhhH',0x10000,800,-200,0,600,0,0,600,1,0,0,0,0,0,0,0,n)
    maxp=pack('IH'+'H'*13,0x10000,n,180,45,0,0,2,0,0,0,0,0,0,0,0)
    hmtx=b''.join(pack('Hh',600,0) for _ in range(n))
    sub=pack('HHHHHHH',4,32,0,4,4,1,0)+pack('HH',126,65535)+pack('H',0)+pack('HH',32,65535)+pack('hh',-31,1)+pack('HH',0,0)
    cmap=pack('HHHHI',0,1,3,1,12)+sub
    namevalue='Subsea Pixel'.encode('utf-16-be');name=pack('HHH',0,2,30)+pack('HHHHHH',3,1,0x409,1,len(namevalue),0)+pack('HHHHHH',3,1,0x409,6,len(namevalue),0)+namevalue
    post=pack('IihhIIIII',0x30000,0,0,0,1,0,0,0,0)
    os2=pack('HhHHH',0,600,400,5,0)+pack('h'*11,*([0]*11))+bytes(10)+pack('IIII',1,0,0,0)+b'SUBS'+pack('HHHhhhHH',64,32,126,800,-200,0,800,200)
    tables={'head':head,'hhea':hhea,'maxp':maxp,'hmtx':hmtx,'glyf':glyf,'loca':b''.join(pack('I',x) for x in locations),'cmap':cmap,'name':name,'post':post,'OS/2':os2}
    def checksum(data):
        data+=b'\0'*((-len(data))%4);return sum(struct.unpack('>'+'I'*(len(data)//4),data))&0xffffffff
    num=len(tables);power=2**(num.bit_length()-1);header=pack('IHHHH',0x10000,num,power*16,power.bit_length()-1,num*16-power*16);offset=12+16*num;directory=b'';body=b'';offsets={}
    for tag,data in sorted(tables.items()):
        offsets[tag]=offset;directory+=tag.encode()+pack('III',checksum(data),offset,len(data));padded=data+b'\0'*((-len(data))%4);body+=padded;offset+=len(padded)
    font=bytearray(header+directory+body);struct.pack_into('>I',font,offsets['head']+8,(0xb1b0afba-checksum(bytes(font)))&0xffffffff)
    (root/'assets').mkdir(exist_ok=True);(root/'assets'/'pixel-font.ttf').write_bytes(font)
if __name__=='__main__':build()
