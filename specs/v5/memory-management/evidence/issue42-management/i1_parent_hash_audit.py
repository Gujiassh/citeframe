"""Read immutable loose and packed objects without Git invocation or repository writes."""
from pathlib import Path
import hashlib, json, zlib
ROOT=Path(__file__).resolve().parents[5]
OBJECTS=Path('D:/Code/citeframe/.git/objects')
REV='7d47607778a9212e9f3cb076442cd7c497c1f8ca'
def packed(oid):
    for index in (OBJECTS/'pack').glob('*.idx'):
        data=index.read_bytes(); n=int.from_bytes(data[1028:1032],'big'); names=data[1032:1032+20*n]
        for i in range(n):
            if names[i*20:i*20+20].hex()==oid:
                offset=int.from_bytes(data[1032+24*n+4*i:1036+24*n+4*i],'big')
                assert offset<2**31
                return unpack(index.with_suffix('.pack').read_bytes(),offset)
    raise FileNotFoundError(oid)
def unpack(data, offset):
    start=offset; c=data[offset];offset+=1;kind=(c>>4)&7;size=c&15;shift=4
    while c&128:
        c=data[offset];offset+=1;size|=(c&127)<<shift;shift+=7
    if kind==6:
        c=data[offset];offset+=1;distance=c&127
        while c&128:
            c=data[offset];offset+=1;distance=((distance+1)<<7)+(c&127)
        basekind,base=unpack(data,start-distance)
    elif kind==7:
        basekind,base=object_data(data[offset:offset+20].hex());offset+=20
    body=zlib.decompress(data[offset:])
    if kind not in (6,7): return {1:'commit',2:'tree',3:'blob',4:'tag'}[kind],body
    pos=0
    def number():
        nonlocal pos
        value=shift=0
        while True:
            c=body[pos];pos+=1;value|=(c&127)<<shift
            if not c&128:return value
            shift+=7
    assert number()==len(base);target=number();out=bytearray()
    while pos<len(body):
        c=body[pos];pos+=1
        if c&128:
            off=count=0
            for j in range(4):
                if c&(1<<j):off|=body[pos]<<(8*j);pos+=1
            for j in range(3):
                if c&(1<<(4+j)):count|=body[pos]<<(8*j);pos+=1
            out.extend(base[off:off+(count or 65536)])
        else:
            assert c;out.extend(body[pos:pos+c]);pos+=c
    assert len(out)==target
    return basekind,bytes(out)
def object_data(oid):
    path=OBJECTS/oid[:2]/oid[2:]
    if path.exists():
        raw=zlib.decompress(path.read_bytes());header,body=raw.split(b'\0',1);kind=header.split()[0].decode()
    else:kind,body=packed(oid)
    assert hashlib.sha1(f'{kind} {len(body)}'.encode()+b'\0'+body).hexdigest()==oid
    return kind,body
def obj(oid): return object_data(oid)[1]
def blob(path):
    tree=obj(REV).splitlines()[0].split()[1].decode()
    for part in path.split('/'):
        data=obj(tree); pos=0; entries={}
        while pos<len(data):
            end=data.index(b'\0',pos); name=data[pos:end].split(b' ',1)[1].decode();entries[name]=data[end+1:end+21].hex();pos=end+21
        tree=entries[part]
    return obj(tree)
def digest(b): return hashlib.sha256(b).hexdigest()
paths=['apps/api/src/ai_pdf_api/main.py','apps/worker/tests/test_multimodal_golden_execution.py',
'docs/evals/artifacts/m402-v1/worker-execution.json','docs/evals/artifacts/m402-v1/real-model-execution.json',
'docs/evals/m402-execution-source-provenance-v1.json','docs/evals/multimodal-failures-v1.json',
'docs/evals/r100-research-cases-v1.json','apps/api/src/ai_pdf_api/services/multimodal_execution.py',
'apps/api/src/ai_pdf_api/services/r100_evaluation.py','apps/api/tests/test_multimodal_execution.py','apps/api/tests/test_r100_research_eval.py']
rows={}
for path in paths:
    parent=blob(path);current=(ROOT/path).read_bytes();normalized=current.replace(b'\r\n',b'\n')
    rows[path]=dict(pristineParentSha256=digest(parent),checkoutSha256=digest(current),normalizedCheckoutSha256=digest(normalized),matchesParent=parent==current,matchesParentAfterCRLFNormalization=parent==normalized)
provenance=json.loads(blob(paths[4])); r100=json.loads(blob(paths[6]))
checks=[]
for entry in provenance['entries']:
    f=entry['executionArtifactPath'];checks.append(dict(path=f,expected=entry['artifactSha256'],parentMatches=digest(blob(f))==entry['artifactSha256'],checkoutMatches=digest((ROOT/f).read_bytes())==entry['artifactSha256']))
f=r100['referenceFailureTaxonomy'];checks.append(dict(path=f['path'],expected=f['sha256'],parentMatches=digest(blob(f['path']))==f['sha256'],checkoutMatches=digest((ROOT/f['path']).read_bytes())==f['sha256']))
main=(ROOT/paths[0]).read_bytes().replace(b'\r\n',b'\n').replace(b'from ai_pdf_api.routers.memories import router as memories_router\n',b'').replace(b'app.include_router(memories_router)\n',b'')
result=dict(pristineParent=REV,method='SHA1-verified immutable object reads; no Git calls',files=rows,historicalHashChecks=checks,mainOnlyTwoRegistrationLines=main==blob(paths[0]))
out=Path(__file__).with_name('i1-parent-hash-audit.json');out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
