"""Make an ITALIC (75 deg, DSTU ISO 3098 / ДСТУ ГОСТ 2.304 type B) copy of a LibreCAD .lff vector font by shearing
every point x' = x + y * tan(15 deg). OpenGOST fonts are OFL-licensed: the copy gets its own name. (Claude)
Зробити КУРСИВНУ (75°) копію векторного шрифту LibreCAD .lff зсувом кожної точки x' = x + y·tg15°.
Шрифти OpenGOST під ліцензією OFL: копія має власну назву.
Usage / запуск: python lff_italic.py <src.lff> <dst.lff> "<New Name>" """
import math, re, sys

K = math.tan(math.radians(15))
src, dst, name = sys.argv[1], sys.argv[2], sys.argv[3]
out = []
num = re.compile(r"^-?\d+(\.\d+)?$")
for line in open(src, encoding="utf-8").read().splitlines():
    s = line.strip()
    if s.startswith("#"):
        if s.lower().startswith("# name:"):
            line = f"# Name:              {name}"
        out.append(line); continue
    if not s or s.startswith("[") or s.startswith("C"):        # glyph header / reference to another glyph
        out.append(line); continue
    pts = []
    ok = True
    for p in s.split(";"):
        parts = p.split(",")
        if len(parts) < 2 or not (num.match(parts[0]) and num.match(parts[1])):
            ok = False; break
        x, y = float(parts[0]), float(parts[1])
        rest = parts[2:]                                        # e.g. A0.5 (arc bulge) / дуга
        pts.append(",".join([f"{x + y * K:.4f}".rstrip("0").rstrip("."), parts[1]] + rest))
    out.append(";".join(pts) if ok else line)
open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("written", dst)
