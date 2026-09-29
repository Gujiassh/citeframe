"""Bounded synthetic Windows/Linux-portable oracles; no source or renderer authority."""
import ast
from dataclasses import FrozenInstanceError
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
from io import BytesIO
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "apps/api/src/ai_pdf_api/modalities/native_image_geometry.py"
spec = importlib.util.spec_from_file_location("geometry_under_test", MODULE_PATH)
geometry = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = geometry
spec.loader.exec_module(geometry)


@pytest.fixture(scope="module")
def engines():
    import pymupdf as fitz
    import PIL
    from PIL import Image
    assert fitz.VersionBind == "1.28.2"
    assert PIL.__version__ == "12.3.0"
    return fitz, Image


@pytest.fixture(scope="module")
def old_oracles(engines):
    fitz, Image = engines
    folder = ROOT / "apps/api/src/ai_pdf_api/modalities"
    # Pin both byte-exact CRLF and LF checkouts of the approved original sources.
    sources = {
        "image_evidence_targets.py": ({"80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7", "6E4D4F41B3A9EF5201A8390CDCA9C17AC36FE2E37D5E6A074ADF753035FB6DD8"}, {"_crop_canonical_image", "_pixel_floor", "_pixel_ceil"}),
        "pdf_evidence_targets.py": ({"9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229", "A520DA2A374FE5289DDE6A109558E068C78908557F030C32278ED8759426398A"}, {"crop_pdf_regions_png"}),
    }
    namespace = dict(Image=Image, BytesIO=BytesIO, Decimal=Decimal, ROUND_FLOOR=ROUND_FLOOR,
                     ROUND_CEILING=ROUND_CEILING, fitz=fitz, EvidenceTargetError=ValueError)
    for filename, (digests, functions) in sources.items():
        raw = (folder / filename).read_bytes()
        assert sha256(raw).hexdigest().upper() in digests, "old oracle source changed"
        tree = ast.parse(raw.decode("utf-8"))
        selected = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
        selected += [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions]
        assert len(selected) == len(functions) + 1
        if filename.startswith("pdf"):
            constants = [node for node in tree.body if isinstance(node, ast.Assign)
                         and any(isinstance(target,ast.Name) and target.id in {"_CROP_DPI","_MAX_CROP_EDGE_PX"} for target in node.targets)]
            assert len(constants) == 2
            selected += constants
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[])),str(folder/filename),"exec"),namespace)
    assert (namespace["_CROP_DPI"], namespace["_MAX_CROP_EDGE_PX"]) == (150,1280)
    return namespace


def region_object(region):
    return SimpleNamespace(**dict(zip(("x","y","width","height"),map(float,region))))


def canonical_png(Image, mode="RGB"):
    image = Image.new(mode,(32,32))
    image.putdata([(x*7,y*7,(x+y)*3) + ((128+(x%2)*127,) if mode=="RGBA" else ()) for y in range(32) for x in range(32)])
    output=BytesIO()
    image.save(output,format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("mode", ["RGB","RGBA"])
def test_png_64_tiny_outputs_preserve_bytes_dimensions_order(engines,old_oracles,record_property,mode):
    _,Image=engines
    payload=canonical_png(Image,mode)
    # Eight targets, each with eight ordered tiny regions, retain all sixty-four outputs.
    groups=[[(x/8,y/8,1/32,1/32) for x in range(8)] for y in range(8)]
    regions=[region for group in groups for region in group]
    with localcontext(Context(prec=28,rounding=ROUND_HALF_EVEN)):
        expected=old_oracles["_crop_canonical_image"](payload,width_pixels=32,height_pixels=32,regions=list(map(region_object,regions)))
    actual=[]
    with Image.open(BytesIO(payload)) as image:
        for region in regions:
            bounds=geometry.png_crop_bounds(width_pixels=32,height_pixels=32,region=region)
            output=BytesIO()
            image.crop(bounds).save(output,format="PNG")
            actual.append(output.getvalue())
    assert len(actual)==64 and tuple(actual)==expected
    record_property("png_count",len(actual))
    record_property("total_png_bytes",sum(map(len,actual)))
    record_property("ordered_png_sha256",sha256(b"".join(actual)).hexdigest())
    for png in actual:
        with Image.open(BytesIO(png)) as crop:
            assert crop.size==(1,1) and crop.mode==mode


@pytest.mark.parametrize("region", [(0,0,1,1),(.1,.2,.3,.4),(0.96875,0.96875,.03125,.03125),(0,0,5e-324,5e-324),(.999,.1,.001,.4)])
def test_png_edge_fractional_parity(engines,old_oracles,region):
    _,Image=engines
    payload=canonical_png(Image,"RGBA")
    with localcontext(Context(prec=28,rounding=ROUND_HALF_EVEN)):
        expected=old_oracles["_crop_canonical_image"](payload,width_pixels=32,height_pixels=32,regions=[region_object(region)])[0]
    bounds=geometry.png_crop_bounds(width_pixels=32,height_pixels=32,region=region)
    with Image.open(BytesIO(payload)) as image:
        output=BytesIO()
        image.crop(bounds).save(output,format="PNG")
    assert output.getvalue()==expected


def test_png_context_is_independent_including_traps(old_oracles):
    from decimal import Inexact, Rounded, Underflow, Subnormal
    region=(.12345678912345678,.1,.23456789123456789,.3)
    dimensions=(2**31-1,1000)
    with localcontext(Context(prec=28,rounding=ROUND_HALF_EVEN)):
        expected=(old_oracles["_pixel_floor"](region[0],dimensions[0]),old_oracles["_pixel_floor"](region[1],dimensions[1]),
                  old_oracles["_pixel_ceil"](region[0],region[2],dimensions[0]),old_oracles["_pixel_ceil"](region[1],region[3],dimensions[1]))
    with localcontext() as ambient:
        ambient.prec=3
        ambient.rounding=ROUND_FLOOR
        ambient.Emin=-2
        ambient.Emax=2
        for signal in (Inexact,Rounded,Underflow,Subnormal): ambient.traps[signal]=True
        assert geometry.png_crop_bounds(width_pixels=dimensions[0],height_pixels=dimensions[1],region=region)==expected
        assert ambient.prec==3 and ambient.traps[Inexact]


def make_pdf(fitz, Image, *, size=(300,400), rotation=0, offset=False, complex_case=None):
    document=fitz.open()
    page=document.new_page(width=size[0],height=size[1])
    page.draw_rect(fitz.Rect(15,25,100,130),color=(.2,.4,.8),fill=(.8,.2,.1))
    page.insert_text((35,70),"Synthetic geometry",fontsize=11)
    if offset:page.set_cropbox(fitz.Rect(20,30,size[0]-15,size[1]-10))
    if complex_case=="annotation":
        page.add_rect_annot(fitz.Rect(40,45,110,120)).update()
    elif complex_case=="transparency":
        page.draw_rect(fitz.Rect(35,40,140,165),color=(0,1,0),fill=(0,1,0),fill_opacity=.3,stroke_opacity=.6)
    elif complex_case=="embedded_image":
        page.insert_image(fitz.Rect(30,40,94,104),stream=canonical_png(Image,"RGBA"))
    elif complex_case in ("negative_media","positive_media"):
        origin=-30 if complex_case=="negative_media" else 30
        page.set_mediabox(fitz.Rect(origin,origin,origin+size[0],origin+size[1]))
    elif complex_case=="userunit_direct":
        document.xref_set_key(page.xref,"UserUnit","1.25")
    elif complex_case=="userunit_inherited":
        parent=int(document.xref_get_key(page.xref,"Parent")[1].split()[0])
        document.xref_set_key(parent,"UserUnit","1.25")
    page.set_rotation(rotation)
    payload=document.tobytes()
    assert len(document)<=12 and len(payload)<=2*1024*1024
    document.close()
    return payload


def assert_pdf_parity(payload,region,engines,old_oracles,monkeypatch,record_property):
    fitz,Image=engines
    old_pixmaps=[]
    original=fitz.Page.get_pixmap
    def capture(page,*args,**kwargs):
        pixmap=original(page,*args,**kwargs)
        old_pixmaps.append((tuple(pixmap.irect),pixmap.xres,pixmap.yres))
        return pixmap
    with monkeypatch.context() as patch:
        patch.setattr(fitz.Page,"get_pixmap",capture)
        expected=old_oracles["crop_pdf_regions_png"](payload,page_number=1,regions=[region_object(region)])[0]
    with fitz.open(stream=payload,filetype="pdf") as document:
        page=document[0]
        display=page.get_displaylist()
        def forbidden(*args,**kwargs):raise AssertionError("planner attempted PDF opening or rendering")
        with monkeypatch.context() as patch:
            patch.setattr(fitz,"open",forbidden)
            patch.setattr(fitz.Page,"get_displaylist",forbidden)
            patch.setattr(fitz.Page,"get_pixmap",forbidden)
            patch.setattr(fitz.DisplayList,"get_pixmap",forbidden)
            patch.setattr(fitz.mupdf,"fz_new_pixmap_with_bbox",forbidden)
            plan=geometry.pdf_render_plan(cropbox=tuple(page.cropbox),display_list_bounds=tuple(display.rect),region=region)
        if plan.matrix is None:
            pixmap=page.get_pixmap(clip=plan.clip,dpi=plan.dpi,alpha=False)
            assert plan.dpi==150 and len(old_pixmaps)==1
        else:
            pixmap=page.get_pixmap(clip=plan.clip,matrix=fitz.Matrix(*plan.matrix),alpha=False)
            assert plan.dpi is None and len(old_pixmaps)==2
        actual=pixmap.tobytes("png")
        assert plan.first_bbox==old_pixmaps[0][0]
        assert plan.final_bbox==tuple(pixmap.irect)==old_pixmaps[-1][0]
        assert (pixmap.xres,pixmap.yres)==old_pixmaps[-1][1:]
        assert (pixmap.xres,pixmap.yres)==((150,150) if plan.matrix is None else (96,96))
        assert actual==expected
        with Image.open(BytesIO(actual)) as new, Image.open(BytesIO(expected)) as old:
            assert new.size==old.size and new.info.get("dpi")==old.info.get("dpi")
        record_property("first_bbox",str(plan.first_bbox))
        record_property("final_bbox",str(plan.final_bbox))
        record_property("dpi",str((pixmap.xres,pixmap.yres)))
        record_property("png_sha256",sha256(actual).hexdigest())
        return plan


@pytest.mark.parametrize("size", [(300,400),(595,842),(612,792)])
@pytest.mark.parametrize("rotation", [0,90,180,270])
@pytest.mark.parametrize("offset", [False,True])
@pytest.mark.parametrize("region", [(0.,0.,1.,1.),(.2,.25,.45,.5)])
def test_pdf_48_actual_old_oracle_matrix(engines,old_oracles,monkeypatch,record_property,size,rotation,offset,region):
    fitz,Image=engines
    payload=make_pdf(fitz,Image,size=size,rotation=rotation,offset=offset)
    plan=assert_pdf_parity(payload,region,engines,old_oracles,monkeypatch,record_property)
    if size in ((595,842),(612,792)) and rotation==0 and not offset and region==(0.,0.,1.,1.):
        assert plan.matrix is not None


@pytest.mark.parametrize("case", ["no_annotation","annotation","transparency","embedded_image","negative_media","positive_media","userunit_direct","userunit_inherited","rounding_low","rounding_high"])
def test_pdf_bounded_complex_old_oracle(engines,old_oracles,monkeypatch,record_property,case):
    fitz,Image=engines
    payload=make_pdf(fitz,Image,complex_case=case,rotation=90 if case=="annotation" else 0)
    region=(.11,.17,.51,.49)
    if case.startswith("rounding"):
        edge=(100+.001 if case=="rounding_high" else 100-.001)/(150/72)/300
        region=(edge,.123,.3,.45)
    assert_pdf_parity(payload,region,engines,old_oracles,monkeypatch,record_property)


class IntSubclass(int):pass
class FloatSubclass(float):pass
class HostileNumber:
    def __float__(self):raise AssertionError("custom numeric coercion")


@pytest.mark.parametrize("value", [True,False,0,-1,2**31,1.0,IntSubclass(1),None,"32",10**500])
def test_strict_png_dimensions(value):
    for field in ("width_pixels","height_pixels"):
        arguments=dict(width_pixels=32,height_pixels=32,region=(0,0,1,1))
        arguments[field]=value
        with pytest.raises(ValueError,match="^native_image_geometry_invalid$"):
            geometry.png_crop_bounds(**arguments)


_BAD_REGIONS=[None,[],(0,0,1),(0,0,1,1,1),(True,0,1,1),(IntSubclass(0),0,1,1),
    (FloatSubclass(0),0,1,1),(HostileNumber(),0,1,1),("0",0,1,1),(float("nan"),0,1,1),
    (0,float("inf"),1,1),(0,0,float("-inf"),1),(-.1,0,.5,.5),(0,0,0,1),(0,0,1,-1),
    (0,0,1.1,1),(.6,0,.5,1),(0,.6,1,.5),(10**500,0,1,1)]


@pytest.mark.parametrize("region", _BAD_REGIONS)
def test_strict_regions_for_both_algorithms(region):
    with pytest.raises(ValueError,match="^native_image_geometry_invalid$"):
        geometry.png_crop_bounds(width_pixels=32,height_pixels=32,region=region)
    with pytest.raises(ValueError,match="^native_image_geometry_invalid$"):
        geometry.pdf_render_plan(cropbox=(0,0,100,100),display_list_bounds=(0,0,100,100),region=region)


@pytest.mark.parametrize("rect", [None,[],(0,0,100),(0,0,0,100),(0,0,100,-1),(0,0,1_000_001,100),(-1_000_001,0,1,1),
    (0,0,float("nan"),100),(0,0,float("inf"),100),(0,0,True,100),(0,0,FloatSubclass(100),100),(0,0,HostileNumber(),100)])
def test_strict_rectangles(rect):
    for field in ("cropbox","display_list_bounds"):
        arguments=dict(cropbox=(0,0,100,100),display_list_bounds=(0,0,100,100),region=(0,0,1,1))
        arguments[field]=rect
        with pytest.raises(ValueError,match="^native_image_geometry_invalid$"):
            geometry.pdf_render_plan(**arguments)


@pytest.mark.parametrize("kind", ["png_edge","pdf_small_clip","pdf_disjoint","pdf_empty_raster"])
def test_empty_results_are_explicit(engines,kind):
    with pytest.raises(ValueError,match="^native_image_geometry_empty$"):
        if kind=="png_edge":
            geometry.png_crop_bounds(width_pixels=32,height_pixels=32,region=(1.,0.,5e-324,1.))
        else:
            display=(0,0,100,100)
            region=(0,0,1,1)
            if kind=="pdf_small_clip":region=(0,0,.004,1)
            if kind=="pdf_disjoint":display=(101,101,102,102)
            if kind=="pdf_empty_raster":display=(.00001,.00001,.00002,.00002)
            geometry.pdf_render_plan(cropbox=(0,0,100,100),display_list_bounds=display,region=region)


def test_pdf_plan_frozen_and_no_handles(engines):
    plan=geometry.pdf_render_plan(cropbox=(0,0,100,100),display_list_bounds=(0,0,100,100),region=(0,0,1,1))
    with pytest.raises(FrozenInstanceError):plan.dpi=72
    assert type(plan.clip) is tuple and type(plan.first_bbox) is tuple and type(plan.final_bbox) is tuple


@pytest.mark.parametrize("fault", ["version","missing_symbol"])
def test_pdf_engine_version_and_symbols_fail_closed(engines,monkeypatch,fault):
    fitz,_=engines
    if fault=="version":monkeypatch.setattr(fitz,"VersionBind","unknown")
    else:monkeypatch.delattr(fitz.mupdf,"fz_round_rect")
    assert geometry.png_crop_bounds(width_pixels=1,height_pixels=1,region=(0,0,1,1))==(0,0,1,1)
    with pytest.raises(ValueError,match="^native_image_geometry_engine_unsupported$"):
        geometry.pdf_render_plan(cropbox=(0,0,10,10),display_list_bounds=(0,0,10,10),region=(0,0,1,1))


def test_pure_file_import_without_apps_engines_or_network():
    # Existing modalities/__init__.py imports application services; this isolated file does not.
    script='''
import importlib.abc,importlib.util,socket,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".",1)[0] in {"ai_pdf_api","ai_pdf_worker","pymupdf","fitz","PIL","citeframe_contracts"}:
            raise ImportError("blocked dependency")
sys.meta_path.insert(0,Block())
def deny(*args,**kwargs):raise AssertionError("network forbidden")
socket.socket=deny
socket.getaddrinfo=deny
spec=importlib.util.spec_from_file_location("isolated_geometry",sys.argv[1])
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
assert module.png_crop_bounds(width_pixels=32,height_pixels=32,region=(0,0,1,1))==(0,0,32,32)
try:module.pdf_render_plan(cropbox=(0,0,10,10),display_list_bounds=(0,0,10,10),region=(0,0,1,1))
except ValueError as error:assert str(error)=="native_image_geometry_engine_unsupported"
else:raise AssertionError("missing engine accepted")
assert not any(name.startswith(("ai_pdf_api","ai_pdf_worker","pymupdf","fitz","PIL")) for name in sys.modules)
'''
    result=subprocess.run([sys.executable,"-B","-c",script,str(MODULE_PATH)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_no_production_caller_and_no_io_or_renderer_calls():
    for path in (ROOT/"apps/api/src").rglob("*.py"):
        if path==MODULE_PATH:continue
        assert "native_image_geometry" not in path.read_text(encoding="utf-8"),str(path)
    tree=ast.parse(MODULE_PATH.read_text(encoding="utf-8-sig"))
    forbidden={"open","get_pixmap","get_displaylist","save","read","write","loads","load","decode","encode"}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ""
            assert name not in forbidden


@pytest.mark.parametrize("fault", ["native_exception", "nonfinite_transform", "invalid_bbox"])
def test_unsafe_native_intermediates_use_safe_invalid_code(engines,monkeypatch,fault):
    fitz,_=engines
    if fault=="native_exception":
        def fail(*args):raise ValueError("synthetic-sensitive-native-detail")
        monkeypatch.setattr(fitz.mupdf,"fz_transform_rect",fail)
    elif fault=="nonfinite_transform":
        monkeypatch.setattr(fitz.mupdf,"fz_transform_rect",lambda *args:fitz.mupdf.FzRect(0,0,float("inf"),1))
    else:
        monkeypatch.setattr(fitz.mupdf,"fz_round_rect",lambda *args:SimpleNamespace(x0=0,y0=0,x1=2**31,y1=1))
    with pytest.raises(ValueError,match="^native_image_geometry_invalid$"):
        geometry.pdf_render_plan(cropbox=(0,0,10,10),display_list_bounds=(0,0,10,10),region=(0,0,1,1))
