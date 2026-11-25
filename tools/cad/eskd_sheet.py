"""DSTU drawing sheet in DXF (ezdxf): layers, line types (DSTU ISO 128), frame and formats (DSTU ISO 5457),
title block FORM 1 with the full grid and Ukrainian labels (DSTU GOST 2.104:2006), graph 26, dimension style
(DSTU ISO 129-1), drafting ITALIC font type B (DSTU ISO 3098 / DSTU GOST 2.304). Claude reference, 24.11.2026.
Аркуш креслення за ДСТУ у DXF (ezdxf): шари, типи ліній (ДСТУ ISO 128), рамка і формати (ДСТУ ISO 5457),
основний напис ФОРМА 1 з повною сіткою і підписами українською (ДСТУ ГОСТ 2.104:2006), графа 26,
розмірний стиль (ДСТУ ISO 129-1), креслярський КУРСИВ тип Б (ДСТУ ISO 3098 / ДСТУ ГОСТ 2.304)."""
from pathlib import Path

import ezdxf

# name -> (ACI colour, linetype, lineweight 1/100 mm)  /  назва -> (колір, тип лінії, товщина)
LAYERS = {
    "CONTOUR": (7, "CONTINUOUS", 50), "THIN": (7, "CONTINUOUS", 25), "AXIS": (1, "CENTER2", 25),
    "HIDDEN": (5, "DASHED2", 25), "DIM": (3, "CONTINUOUS", 18), "HATCH": (8, "CONTINUOUS", 18),
    "TEXT": (7, "CONTINUOUS", 25), "FRAME": (7, "CONTINUOUS", 50),
}
FORMATS = {"A0": (1189, 841), "A1": (841, 594), "A2": (594, 420), "A3": (420, 297), "A4": (210, 297)}
SPEC_COLS = (6, 6, 8, 70, 63, 10, 22)                  # Specification table column widths / Ширини стовпців специфікації
SPEC_HEAD = ("Формат", "Зона", "Поз.", "Позначення", "Найменування", "Кіл.", "Примітка")  # Specification header / Шапка специфікації
TB_W, TB_H = 185, 55                                   # form 1 / форма 1
FONT_H = 3.5                                           # DSTU ISO 3098 type B, 3.5 mm / шрифт 3,5 мм
# Text style: NAME = LibreCAD font (it picks the font by style name), FONT = the TTF for AutoCAD / BricsCAD.
# OpenGOST Type B has Cyrillic and the Ø sign. / Стиль: НАЗВА — шрифт LibreCAD (він бере шрифт за назвою стилю),
# ФАЙЛ — TTF для AutoCAD. OpenGOST тип Б має кирилицю і знак Ø.
TEXT_STYLE = "dante_dstu_b_i"                         # italic copy of OpenGOST B (C:\DANTE\fonts\lff)
TEXT_FONT = "OpenGostTypeB-Regular.ttf"
OBLIQUE = 15.0                                         # DSTU ISO 3098: letters at 75 deg / літери під 75°
LEFT_COLS = (7, 10, 23, 15, 10)                        # Зм., Арк., № докум., Підпис, Дата
NAMES = ("Розроб.", "Перевір.", "Т.контр.", "", "Н.контр.", "Затв.")   # bottom-up order reversed below


def _rect(msp, x0, y0, x1, y1, layer):
    return msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _line(msp, a, b, layer):
    msp.add_line(a, b, dxfattribs={"layer": layer})


def _text(msp, s, x, y, h=FONT_H, align="MIDDLE_CENTER", rot=0, width=1.0):
    """ESKD text: style ESKD (GOST type B, slant 15 deg) / Текст ЄСКД: стиль ESKD (тип Б, нахил 15°)."""
    from ezdxf.enums import TextEntityAlignment
    # Italic drafting font: 75 deg letters = oblique 15 deg on every text (LibreCAD and AutoCAD both honour it)
    # Креслярський курсив: нахил літер 75° = нахил 15° у кожному тексті (враховують і LibreCAD, і AutoCAD)
    t = msp.add_text(s, height=h, rotation=rot, dxfattribs={"layer": "TEXT", "style": TEXT_STYLE, "oblique": OBLIQUE})
    t.dxf.width = width                                # narrow labels fit the cells / вужчі підписи влазять у графи
    t.set_placement((x, y), align=getattr(TextEntityAlignment, align))
    return t


def _setup(doc):
    doc.header["$INSUNITS"] = 4                        # mm / міліметри
    doc.header["$MEASUREMENT"] = 1                     # metric / метрична
    doc.header["$LWDISPLAY"] = 1                       # show line weights / показувати товщини
    doc.header["$LTSCALE"] = 1.0
    # Standard AutoCAD names (acad.lin / LibreCAD know them): CENTER2 = dash-dot, DASHED2 = dashed (DSTU ISO 128-20)
    # Стандартні назви AutoCAD (їх знають і LibreCAD): CENTER2 — штрихпунктир, DASHED2 — штрихова (ДСТУ ISO 128-20)
    # Drawing-wide dimension defaults: LibreCAD reads the header, not only the style / Загальні розмірні змінні
    for k, v in dict(DIMTXT=FONT_H, DIMASZ=3.0, DIMEXE=2.0, DIMEXO=0.0, DIMGAP=1.0, DIMTAD=1, DIMTIH=0, DIMTOH=0,
                     DIMDEC=0, DIMZIN=8, DIMSCALE=1.0, DIMLUNIT=2, DIMADEC=0, DIMTSZ=0.0, DIMCLRD=3, DIMCLRE=3,
                     DIMCLRT=3).items():
        doc.header["$" + k] = v
    for name, (color, lt, lw) in LAYERS.items():
        doc.layers.add(name, color=color, linetype=lt, lineweight=lw)
    doc.header["$DWGCODEPAGE"] = "ANSI_1251"             # Cyrillic / кирилиця
    st = doc.styles.add(TEXT_STYLE, font=TEXT_FONT)
    st.dxf.oblique = OBLIQUE                                # 75 deg letters / нахил 75°
    st.dxf.width = 0.8
    ds = doc.dimstyles.new("ESKD")
    for k, v in dict(dimtxt=FONT_H, dimasz=3.0, dimexe=2.0, dimexo=0.0, dimgap=1.0, dimtad=1, dimtih=0, dimtoh=0,
                     dimdec=0, dimzin=8, dimtxsty=TEXT_STYLE, dimclrd=3, dimclre=3, dimclrt=3, dimlwd=18, dimlwe=18,
                     dimblk="", dimscale=1.0, dimlunit=2).items():
        ds.dxf.set(k, v)
    doc.header["$DIMSTYLE"] = "ESKD"
    doc.header["$LUPREC"] = 0                          # whole millimetres / цілі міліметри


def title_block(msp, x0, y0, title="", code="", org="", author="", checker="", material="", scale="1:1",
                sheet="1", sheets="1", mass=""):
    """Form 1 (185 x 55) with the full grid; (x0, y0) is its bottom-left corner.
    Форма 1 (185 x 55) з повною сіткою; (x0, y0) — її лівий нижній кут."""
    X = lambda dx: x0 + dx
    Y = lambda dy: y0 + dy
    _rect(msp, X(0), Y(0), X(TB_W), Y(TB_H), "FRAME")
    # left block 65 mm: 11 rows of 5 mm, header row 30-35 / ліва частина: 11 рядків по 5 мм
    _line(msp, (X(65), Y(0)), (X(65), Y(55)), "FRAME")
    for k in range(1, 11):
        _line(msp, (X(0), Y(5 * k)), (X(65), Y(5 * k)), "FRAME" if k in (6, 7) else "THIN")
    xs = [0]
    for w in LEFT_COLS:
        xs.append(xs[-1] + w)
    for i, x in enumerate(xs[1:-1], 1):
        _line(msp, (X(x), Y(30)), (X(x), Y(55)), "FRAME")         # changes + header / зміни + шапка
    for x in (xs[2], xs[3], xs[4]):                    # name rows: 17 | 23 | 15 | 10 / рядки прізвищ
        _line(msp, (X(x), Y(0)), (X(x), Y(30)), "FRAME")
    for lab, x in zip(("Зм.", "Арк.", "№ докум.", "Підпис", "Дата"), xs[:-1]):
        w = LEFT_COLS[xs.index(x)]
        _text(msp, lab, X(x + w / 2), Y(32.5), h=2.5, width=0.7)
    for row, lab in enumerate(NAMES):                  # from top: Розроб. at 25-30 / згори вниз
        if lab:
            _text(msp, lab, X(1), Y(27.5 - 5 * row), h=2.5, align="MIDDLE_LEFT", width=0.8)
    if author:
        _text(msp, author, X(17 + 1), Y(27.5), h=2.5, align="MIDDLE_LEFT")
    if checker:
        _text(msp, checker, X(17 + 1), Y(22.5), h=2.5, align="MIDDLE_LEFT")
    # right part / права частина
    _line(msp, (X(65), Y(40)), (X(185), Y(40)), "FRAME")            # graph 2 band 15 mm / графа 2
    _line(msp, (X(65), Y(15)), (X(185), Y(15)), "FRAME")
    _line(msp, (X(135), Y(0)), (X(135), Y(40)), "FRAME")
    _line(msp, (X(135), Y(35)), (X(185), Y(35)), "FRAME")
    _line(msp, (X(135), Y(20)), (X(185), Y(20)), "FRAME")
    _line(msp, (X(150), Y(20)), (X(150), Y(40)), "FRAME")           # Літ. 3 x 5 / Mass 17 / Scale 18
    _line(msp, (X(167), Y(20)), (X(167), Y(40)), "FRAME")
    for x in (140, 145):
        _line(msp, (X(x), Y(20)), (X(x), Y(35)), "THIN")
    _line(msp, (X(155), Y(15)), (X(155), Y(20)), "FRAME")           # Аркуш 20 | Аркушів 30
    _text(msp, "Літ.", X(142.5), Y(37.5), h=2.5)
    _text(msp, "Маса", X(158.5), Y(37.5), h=2.5)
    _text(msp, "Масштаб", X(176), Y(37.5), h=2.5)
    _text(msp, f"Аркуш {sheet}", X(145), Y(17.5), h=2.5)
    _text(msp, f"Аркушів {sheets}", X(170), Y(17.5), h=2.5)
    _text(msp, scale, X(176), Y(27.5), h=FONT_H)
    if mass:
        _text(msp, mass, X(158.5), Y(27.5), h=FONT_H)
    if code:
        _text(msp, code, X(125), Y(47.5), h=7)                       # graph 2 / позначення
    if title:
        _text(msp, title, X(100), Y(27.5), h=5)                      # graph 1 / найменування
    if material:
        _text(msp, material, X(100), Y(7.5), h=FONT_H)               # graph 3 / матеріал
    if org:
        _text(msp, org, X(160), Y(7.5), h=FONT_H)                    # graph 9 / організація


def new_sheet(fmt="A4", title="", code="", org="", author="", checker="", material="", scale="1:1"):
    """New ESKD sheet / Новий аркуш ЄСКД."""
    W, H = FORMATS[fmt]
    doc = ezdxf.new("R2010", setup=True)
    _setup(doc)
    msp = doc.modelspace()
    _rect(msp, 0, 0, W, H, "THIN")                                   # trimmed sheet edge / край аркуша
    _rect(msp, 20, 5, W - 5, H - 5, "FRAME")                         # frame: 20 left, 5 others / рамка
    title_block(msp, W - 5 - TB_W, 5, title, code, org, author, checker, material, scale)
    # graph 26: 70 x 14 in the top-left corner, code turned 180 deg / графа 26
    _rect(msp, 20, H - 5 - 14, 20 + 70, H - 5, "FRAME")
    if code:
        _text(msp, code, 20 + 35, H - 5 - 7, h=5, rot=180)
    return doc


def _n(v):
    """100.0 -> '100', 12.5 -> '12,5' (ESKD decimal comma) / десяткова кома за ЄСКД."""
    return (f"{v:g}").replace(".", ",")


def add_part(doc, x, y, w, h, hole_d=0):
    """Plate w x h with axes (3 mm beyond the contour), hole, ESKD dimensions incl. diameter.
    Пластина з осями (3 мм за контур), отвором і розмірами ЄСКД, зокрема діаметр."""
    msp = doc.modelspace()
    _rect(msp, x, y, x + w, y + h, "CONTOUR")
    cx, cy = x + w / 2, y + h / 2
    _line(msp, (x - 3, cy), (x + w + 3, cy), "AXIS")
    _line(msp, (cx, y - 3), (cx, y + h + 3), "AXIS")
    if hole_d > 0:
        msp.add_circle((cx, cy), hole_d / 2, dxfattribs={"layer": "CONTOUR"})
        # explicit texts: every CAD shows them the same (LibreCAD ignores DIMDEC) / явний текст — однаково в усіх САПР
        d = msp.add_diameter_dim(center=(cx, cy), radius=hole_d / 2, angle=45, dimstyle="ESKD", text=f"%%c{_n(hole_d)}",
                                 override={"dimtmove": 0}, dxfattribs={"layer": "DIM"})
        d.render()
    msp.add_linear_dim(base=(x, y - 10), p1=(x, y), p2=(x + w, y), dimstyle="ESKD", text=_n(w),
                       dxfattribs={"layer": "DIM"}).render()
    msp.add_linear_dim(base=(x + w + 10, y), p1=(x + w, y), p2=(x + w, y + h), angle=90, dimstyle="ESKD", text=_n(h),
                       dxfattribs={"layer": "DIM"}).render()
    return doc


def add_hatch(doc, points, angle=45, spacing=2.0):
    """Add a hatch with ANSI31 pattern / Додати штрихування з шаблоном ANSI31."""
    msp = doc.modelspace()
    h = msp.add_hatch(dxfattribs={"layer": "HATCH", "pattern_name": "ANSI31"})
    h.set_pattern_fill("ANSI31", scale=spacing / 3.175, angle=angle)
    h.paths.add_polyline_path(points, is_closed=True)
    return h


def add_spec(doc, x, y, rows):
    """Draw a specification table and return the bottom y / Намалювати таблицю специфікації та повернути нижній y."""
    msp = doc.modelspace()
    row_h = 8
    head_h = 15
    total_h = head_h + len(rows) * row_h
    
    # Draw outer frame / Намалювати зовнішню рамку
    _rect(msp, x, y - total_h, x + 185, y, "FRAME")
    
    # Header separator line / Лінія розділення шапки
    _line(msp, (x, y - head_h), (x + 185, y - head_h), "FRAME")
    
    # Compute column X coordinates / Обчислити координати X стовпців
    col_xs = [x]
    for w in SPEC_COLS:
        col_xs.append(col_xs[-1] + w)
        
    # Draw vertical lines for columns (header and rows) / Намалювати вертикальні лінії для стовпців
    for cx in col_xs[1:-1]:
        _line(msp, (cx, y - total_h), (cx, y), "FRAME")
        
    # Draw horizontal lines for rows / Намалювати горизонтальні лінії для рядків
    for r in range(1, len(rows)):
        ry = y - head_h - r * row_h
        _line(msp, (x, ry), (x + 185, ry), "FRAME")
        
    # Fill header texts / Заповнити текст шапки
    for i, title in enumerate(SPEC_HEAD):
        cx = col_xs[i] + SPEC_COLS[i] / 2
        _text(msp, title, cx, y - head_h / 2, h=2.5, width=0.8)
        
    # Fill row texts / Заповнити текст рядків
    for r_idx, (pos, code, name, qty) in enumerate(rows):
        ry = y - head_h - r_idx * row_h - row_h / 2
        row_data = ("", "", pos, code, name, qty, "")
        for i, val in enumerate(row_data):
            if val:
                cx = col_xs[i] + SPEC_COLS[i] / 2
                align = "MIDDLE_LEFT" if i in (3, 4, 6) else "MIDDLE_CENTER"
                text_x = col_xs[i] + 1 if align == "MIDDLE_LEFT" else cx
                _text(msp, val, text_x, ry, h=2.5, align=align, width=0.9)
                
    return y - total_h


def save(doc, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path, encoding="utf-8")
    return path
