# Elegant .docx generator v2 — uses the ORIGINAL AWC workshop docx as the
# template shell and reproduces its design language: spaced-caps eyebrows,
# Cambria 56 title, teal divider, label/value meta block, EEF6FA-headed
# tables with padded cells, real restarting step numbering, teal callouts,
# amber screenshot drop-boxes, embedded diagrams.
import io, os, re, zipfile
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.docx")
CW = os.path.join(ROOT, "courseware", "RETAIL")
DIAG_APP = os.path.join(ROOT, "glossary_generator", "diagrams")
DIAG_LAB = os.path.join(ROOT, "data_sources", "lab", "diagrams")

TEAL = "1C7293"; GRAY = "5B7886"; LABEL = "5B7782"; INK = "14333F"; SUB = "065A82"
CELLBORD = "C9DEE8"; HDRFILL = "EEF6FA"; CODEFILL = "F4F7F9"

_tzf = zipfile.ZipFile(TEMPLATE)
TPARTS = {i.filename: _tzf.read(i.filename) for i in _tzf.infolist()
          if not i.filename.startswith("word/media/")}
TINFOS = [i for i in _tzf.infolist() if not i.filename.startswith("word/media/")]
_tzf.close()
SECTPR = re.search(r"<w:sectPr\b.*</w:sectPr>", TPARTS["word/document.xml"].decode("utf-8"), re.S).group(0)

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+?\*\*|\*[^*]+?\*|\[[^\]]+\]\([^)]+\))")

def runs_of(text, base_bold=False, color=None, sz=None):
    out = []
    for tok in INLINE.split(text):
        if not tok:
            continue
        bold, ital, mono, t = base_bold, False, False, tok
        if tok.startswith("`") and tok.endswith("`") and len(tok) > 1:
            mono, t = True, tok[1:-1]
        elif tok.startswith("**") and tok.endswith("**"):
            bold, t = True, tok[2:-2]
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            ital, t = True, tok[1:-1]
        elif tok.startswith("[") and "](" in tok:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", tok)
            t = m.group(1)
            if m.group(2).startswith("http"):
                t += " (" + m.group(2) + ")"
        pr = []
        if bold: pr.append("<w:b/><w:bCs/>")
        if ital: pr.append("<w:i/><w:iCs/>")
        if mono:
            pr.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:color w:val="0A5560"/>'
                      + ('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % ((sz or 20), (sz or 20))))
        else:
            if color: pr.append('<w:color w:val="%s"/>' % color)
            if sz: pr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz))
        rpr = "<w:rPr>%s</w:rPr>" % "".join(pr) if pr else ""
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, esc(t)))
    return "".join(out) or '<w:r><w:t xml:space="preserve"></w:t></w:r>'

def P(runs, style=None, ppr=""):
    pp = ""
    if style or ppr:
        pp = "<w:pPr>%s%s</w:pPr>" % ('<w:pStyle w:val="%s"/>' % style if style else "", ppr)
    return "<w:p>%s%s</w:p>" % (pp, runs)

def spaced_caps(text, color, sz=None, spacing=30):
    pr = '<w:b/><w:bCs/><w:color w:val="%s"/><w:spacing w:val="%d"/>' % (color, spacing)
    if sz: pr += '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz)
    return '<w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>' % (pr, esc(text))

def cover(cfg):
    b = []
    b.append(P(spaced_caps(cfg["eyebrow1"], TEAL), ppr='<w:spacing w:before="1200"/>'))
    b.append(P(spaced_caps(cfg["eyebrow2"], GRAY), ppr='<w:spacing w:before="80"/>'))
    b.append(P(spaced_caps(cfg["label"], LABEL, sz=32, spacing=20), ppr='<w:spacing w:before="200"/>'))
    b.append(P('<w:r><w:rPr><w:rFonts w:ascii="Cambria" w:eastAsia="Cambria" w:hAnsi="Cambria" w:cs="Cambria"/>'
               '<w:b/><w:bCs/><w:color w:val="%s"/><w:sz w:val="56"/><w:szCs w:val="56"/></w:rPr>'
               '<w:t xml:space="preserve">%s</w:t></w:r>' % (INK, esc(cfg["title"])),
               ppr='<w:spacing w:before="320"/>'))
    b.append(P(runs_of(cfg["subtitle"], color=SUB, sz=28), ppr='<w:spacing w:before="200"/>'))
    b.append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="8" w:color="%s"/></w:pBdr>'
             '<w:spacing w:before="500"/></w:pPr></w:p>' % TEAL)
    for i, (k, v) in enumerate(cfg["meta"]):
        b.append(P('<w:r><w:rPr><w:b/><w:bCs/><w:color w:val="%s"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
                   '<w:t xml:space="preserve">%s:  </w:t></w:r>'
                   '<w:r><w:rPr><w:color w:val="%s"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
                   '<w:t xml:space="preserve">%s</w:t></w:r>' % (LABEL, esc(k), INK, esc(v)),
                   ppr='<w:spacing w:before="%d"/>' % (200 if i == 0 else 80)))
    return "".join(b)

class Doc:
    def __init__(self):
        self.body = []
        self.numids = []          # fresh decimal lists
        self.images = []
    def new_numid(self):
        nid = 100 + len(self.numids)
        self.numids.append(nid)
        return nid

def bullet(text, level=0):
    ind = '<w:ind w:left="%d"/>' % (720 + level * 360) if level else ""
    return P(runs_of(text),
             ppr='<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/>'
                 '<w:numId w:val="2"/></w:numPr>%s<w:spacing w:after="60"/>' % ind)

def step(text, numid):
    return P(runs_of(text),
             ppr='<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/>'
                 '<w:numId w:val="%d"/></w:numPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/>' % numid)

def codeblock(lines):
    out = []
    for j, l in enumerate(lines):
        out.append(P('<w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/>'
                     '<w:szCs w:val="19"/><w:color w:val="0A3D52"/></w:rPr>'
                     '<w:t xml:space="preserve">%s</w:t></w:r>' % esc(l or " "),
                     ppr='<w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="%s"/></w:pBdr>'
                         '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
                         '<w:spacing w:before="0" w:after="%d"/><w:ind w:left="240"/>'
                         % (TEAL, CODEFILL, 120 if j == len(lines) - 1 else 0)))
    return "".join(out)

def shot_box(caption):
    borders = "".join('<w:%s w:val="dashed" w:sz="8" w:space="6" w:color="C8A028"/>' % s
                      for s in ("top", "left", "bottom", "right"))
    return P('<w:r><w:rPr><w:b/><w:bCs/><w:color w:val="8A6D1A"/></w:rPr>'
             '<w:t xml:space="preserve">%s</w:t></w:r>' % esc("\U0001F4F7  SCREENSHOT — " + caption),
             ppr='<w:pBdr>%s</w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="FFF7E0"/>'
                 '<w:jc w:val="center"/><w:spacing w:before="120" w:after="200"/>'
                 '<w:ind w:left="240" w:right="240"/>' % borders)

def quote_block(text):
    return P(runs_of(text),
             ppr='<w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="%s"/></w:pBdr>'
                 '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
                 '<w:ind w:left="240" w:right="240"/><w:spacing w:before="120" w:after="160"/>' % (SUB, HDRFILL))

def table(rows):
    ncols = max(len(r) for r in rows)
    if ncols == 2:
        widths = [2900, 6460]
    elif ncols == 3:
        widths = [2500, 3430, 3430]
    else:
        widths = [9360 // ncols] * ncols
    borders = ('<w:tblBorders>' + "".join(
        '<w:%s w:val="single" w:sz="4" w:space="0" w:color="%s"/>' % (s, CELLBORD)
        for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders>")
    grid = "<w:tblGrid>%s</w:tblGrid>" % "".join('<w:gridCol w:w="%d"/>' % w for w in widths)
    mar = ('<w:tcMar><w:top w:w="120" w:type="dxa"/><w:left w:w="180" w:type="dxa"/>'
           '<w:bottom w:w="120" w:type="dxa"/><w:right w:w="180" w:type="dxa"/></w:tcMar>')
    trs = []
    for i, row in enumerate(rows):
        tcs = []
        for j in range(ncols):
            cell = row[j] if j < len(row) else ""
            extra = ""
            if i == 0:
                extra = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % HDRFILL
                if j == 0:
                    extra += ('<w:tcBorders><w:left w:val="single" w:sz="12" w:space="0" w:color="%s"/></w:tcBorders>'
                              % SUB)
            content = P(runs_of(cell, base_bold=(i == 0)), ppr='<w:spacing w:after="0"/>')
            tcs.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s%s</w:tcPr>%s</w:tc>'
                       % (widths[j], extra, mar, content))
        trs.append("<w:tr>%s</w:tr>" % "".join(tcs))
    return ('<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>%s</w:tblPr>%s%s</w:tbl>'
            '<w:p><w:pPr><w:spacing w:after="120"/></w:pPr></w:p>' % (borders, grid, "".join(trs)))

def drawing(rid, name, path, width_in=6.3):
    w, h = Image.open(path).size
    cx = int(width_in * 914400); cy = int(cx * h / w)
    did = rid.replace("rId", "")
    return ('<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="160"/></w:pPr><w:r><w:drawing>'
      '<wp:inline distT="0" distB="0" distL="0" distR="0" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
      '<wp:extent cx="%d" cy="%d"/><wp:docPr id="%s" name="%s"/>'
      '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
      '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
      '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
      '<pic:nvPicPr><pic:cNvPr id="%s" name="%s"/><pic:cNvPicPr/></pic:nvPicPr>'
      '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
      '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
      '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
      % (cx, cy, did, name, did, name, rid, cx, cy))

SHOT = re.compile(r"`?\[SCREENSHOT:\s*([^\]]+)\]`?")
META_LINE = re.compile(r"^\*\*(Primary role|Estimated time|Track|Audience|App version|Focus):?\*\*")

def convert(md_path, cfg):
    doc = Doc()
    lines = io.open(md_path, encoding="utf-8").read().splitlines()
    doc.body.append(cover(cfg))
    embeds = dict(cfg.get("embeds", {}))
    i, cur_numid = 0, None

    # skip original front matter: first h1, italic subtitle(s), bold meta lines
    while i < len(lines):
        t = lines[i].strip()
        if t.startswith("## "):
            break
        if t.startswith("# ") or META_LINE.match(t) or t in ("", "---"):
            i += 1
            continue
        if t.startswith("*") and not t.startswith("**"):
            while i < len(lines) and lines[i].strip():
                stop = lines[i].strip().endswith("*")
                i += 1
                if stop:
                    break
            continue
        break

    def flush_shots(text):
        shots = SHOT.findall(text)
        text = SHOT.sub("", text).rstrip().rstrip("`").rstrip()
        return text, shots

    while i < len(lines):
        raw = lines[i]
        ln = raw.strip()

        if ln.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            doc.body.append(codeblock(block)); cur_numid = None; continue

        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-|]+\|?\s*$", lines[i + 1].strip()):
            rows = [[c.strip() for c in ln.strip("|").split("|")]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            doc.body.append(table(rows)); continue

        if ln.startswith(">"):
            qt = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                qt.append(lines[i].strip().lstrip(">").strip()); i += 1
            doc.body.append(quote_block(" ".join(q for q in qt if q))); cur_numid = None; continue

        if ln.startswith("## "):
            h = ln[3:].strip()
            for key, (rid, name, path) in list(embeds.items()):
                if h.startswith(key):
                    doc.body.append(drawing(rid, name, path))
                    doc.images.append((rid, name, path))
                    del embeds[key]
            doc.body.append(P(runs_of(h), style="Heading1")); cur_numid = None; i += 1; continue
        if ln.startswith("### "):
            h3 = ln[4:].strip()
            for key, (rid, name, path) in list(embeds.items()):
                if h3.startswith(key):
                    doc.body.append(drawing(rid, name, path))
                    doc.images.append((rid, name, path))
                    del embeds[key]
            doc.body.append(P(runs_of(h3), style="Heading2")); cur_numid = None; i += 1; continue

        m = re.match(r"^(\s*)- (.*)$", raw)
        if m:
            level = 1 if len(m.group(1)) >= 2 else 0
            text = m.group(2)
            if text.startswith("[ ] "):
                text = "☐  " + text[4:]
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                  and not re.match(r"^\s*(-|\||```|\d+\. )", lines[i]):
                text += " " + lines[i].strip(); i += 1
            text, shots = flush_shots(text)
            if text: doc.body.append(bullet(text, level))
            for c in shots: doc.body.append(shot_box(c))
            cur_numid = None
            continue

        m = re.match(r"^(\d+)\. (.*)$", ln)
        if m:
            if cur_numid is None or m.group(1) == "1":
                if m.group(1) == "1" or cur_numid is None:
                    cur_numid = doc.new_numid() if (m.group(1) == "1" or cur_numid is None) else cur_numid
            text = m.group(2)
            i += 1
            while i < len(lines) and lines[i].startswith("   ") and lines[i].strip() \
                  and not re.match(r"^\s*(\||```|- )", lines[i]):
                text += " " + lines[i].strip(); i += 1
            text, shots = flush_shots(text)
            if text: doc.body.append(step(text, cur_numid))
            for c in shots: doc.body.append(shot_box(c))
            continue

        if ln in ("---", ""):
            i += 1; continue

        text = ln
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(#|\||>|-|\d+\. |```|---)", lines[i]):
            text += " " + lines[i].strip(); i += 1
        text, shots = flush_shots(text)
        if text:
            doc.body.append(P(runs_of(text), ppr='<w:spacing w:after="120"/>'))
        for c in shots: doc.body.append(shot_box(c))
        cur_numid = None

    return doc

def build(out_path, doc, cfg):
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
           '<w:body>' + "".join(doc.body) + SECTPR + "</w:body></w:document>")
    rels = TPARTS["word/_rels/document.xml.rels"].decode("utf-8")
    rels = re.sub(r'<Relationship [^>]*Type="[^"]*/image"[^>]*/>', "", rels)  # template's stripped media
    for rid, name, path in doc.images:
        rels = rels.replace("</Relationships>",
          '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/%s.png"/></Relationships>' % (rid, name))
    ct = TPARTS["[Content_Types].xml"].decode("utf-8")
    if 'Extension="png"' not in ct:
        ct = ct.replace("</Types>", '<Default Extension="png" ContentType="image/png"/></Types>')
    # numbering: fresh decimal instances (restart per list) on abstract 23
    numbering = TPARTS["word/numbering.xml"].decode("utf-8")
    extra = "".join('<w:num w:numId="%d"><w:abstractNumId w:val="23"/>'
                    '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>' % nid
                    for nid in doc.numids)
    numbering = numbering.replace("</w:numbering>", extra + "</w:numbering>")
    header = TPARTS["word/header1.xml"].decode("utf-8").replace(
        "Workshop 1: Connect the Data Sources", esc(cfg["header"]))
    footer = TPARTS["word/footer1.xml"].decode("utf-8")
    def _fix_footer(m):
        t = m.group(2)
        if "Arizona" in t:
            t = t.replace("Arizona Water Company", "Copper State Credit Union")
            t = t.replace("Arizona Water", "Copper State Credit Union")
            t = t.replace("Arizona", "Copper State Credit Union")
        elif "Water" in t or "Company" in t:
            t = t.replace("Water", "").replace("Company", "").lstrip()
        return m.group(1) + t + m.group(3)
    footer = re.sub(r"(<w:t[^>]*>)([^<]*)(</w:t>)", _fix_footer, footer)
    core = TPARTS["docProps/core.xml"].decode("utf-8")
    core = re.sub(r"<dc:title>[^<]*</dc:title>", "<dc:title>%s</dc:title>" % esc(cfg["title"]), core)
    core = re.sub(r"<dc:creator>[^<]*</dc:creator>", "<dc:creator>Copper State Credit Union - PDC BA Course</dc:creator>", core)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in TINFOS:
            data = {"word/document.xml": xml.encode("utf-8"),
                    "word/_rels/document.xml.rels": rels.encode("utf-8"),
                    "[Content_Types].xml": ct.encode("utf-8"),
                    "word/numbering.xml": numbering.encode("utf-8"),
                    "word/header1.xml": header.encode("utf-8"),
                    "word/footer1.xml": footer.encode("utf-8"),
                    "docProps/core.xml": core.encode("utf-8")}.get(item.filename) or TPARTS[item.filename]
            out.writestr(item.filename, data)
        for rid, name, path in doc.images:
            out.writestr("word/media/%s.png" % name, open(path, "rb").read())
    open(out_path, "wb").write(buf.getvalue())
    z2 = zipfile.ZipFile(out_path)
    assert z2.testzip() is None
    import xml.dom.minidom
    xml.dom.minidom.parseString(z2.read("word/document.xml"))

TWO_APPS = os.path.join(DIAG_APP, "two-apps.png")
SPINE = os.path.join(DIAG_APP, "registry-spine.png")
CHALLENGE = os.path.join(DIAG_APP, "challenge-and-goal.png")
TOPO = os.path.join(DIAG_LAB, "lab-topology.png")
SHARED = os.path.join(DIAG_LAB, "shared-lab.png")
E1 = "PENTAHO DATA CATALOG 11.0.0  ·  BUSINESS ANALYST"
DS = "Canyon Trail Outfitters (cto_retail + cto-documents)"

DOCS = [
 ("Workshop-00-Preflight/Workshop-00-Guide.md", "Workshop-00-Preflight/Workshop-00-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  USERS & ROLES", label="WORKSHOP 0",
       title="Preflight: Provision Users & Roles",
       subtitle="Build the CTO cast — nine users across all seven PDC roles — so every later action lands on a named, least-privilege account.",
       meta=[("Primary role", "IT Administrator / Catalog Admin"), ("Estimated time", "20 minutes"),
             ("Dataset", "Canyon Trail Outfitters (users.csv)")],
       header="Workshop 0: Preflight — Users & Roles")),
 ("Workshop-01-Connect-Data-Sources/Workshop-01-Guide.md", "Workshop-01-Connect-Data-Sources/Workshop-01-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  METADATA INGEST", label="WORKSHOP 1",
       title="Connect the Data Sources",
       subtitle="Bring the Canyon Trail Outfitters database and document store under catalog governance.",
       meta=[("Primary role", "Data Steward / IT Administrator"), ("Estimated time", "120 minutes"),
             ("Dataset", DS)],
       header="Workshop 1: Connect the Data Sources",
       embeds={"Before you begin": ("rId101", "lab-topology", TOPO)})),
 ("Workshop-02-Structure-and-Metadata/Workshop-02-Guide.md", "Workshop-02-Structure-and-Metadata/Workshop-02-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  STRUCTURE & METADATA", label="WORKSHOP 2",
       title="Explore Structure & Metadata",
       subtitle="Read what the ingest captured — schemas, columns, comments and documents — through analyst eyes.",
       meta=[("Primary role", "Business Analyst"), ("Estimated time", "60 minutes"), ("Dataset", DS)],
       header="Workshop 2: Explore Structure & Metadata")),
 ("Workshop-03-Glossary-Terms/Workshop-03-Guide.md", "Workshop-03-Glossary-Terms/Workshop-03-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  BUSINESS GLOSSARY", label="WORKSHOP 3",
       title="Build the Business Glossary",
       subtitle="Give CTO one governed vocabulary: build, import, link and steward the terms — then feed each table's Trust Score.",
       meta=[("Primary role", "Business Steward"), ("Estimated time", "60 minutes"),
             ("Dataset", DS)],
       header="Workshop 3: Build the Business Glossary",
       embeds={"Part B": ("rId101", "two-apps", TWO_APPS)})),
 ("Workshop-04-Profiling-and-Quality/Workshop-04-Guide.md", "Workshop-04-Profiling-and-Quality/Workshop-04-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  PROFILING & QUALITY", label="WORKSHOP 4",
       title="Profile Data & Assess Quality",
       subtitle="Profile CTO's tables to generate statistics, discover keys, make the Trust Score real — and score the compliance obligations as business rules.",
       meta=[("Primary role", "Data Steward / Data Developer"), ("Estimated time", "90 minutes"),
             ("Dataset", DS)],
       header="Workshop 4: Profile Data & Assess Quality")),
 ("Workshop-05-Data-Identification/Workshop-05-Guide.md", "Workshop-05-Data-Identification/Workshop-05-Guide.docx",
  dict(eyebrow1=E1, eyebrow2="PDC PROCESS  ·  DATA IDENTIFICATION", label="WORKSHOP 5",
       title="Data Identification",
       subtitle="How PDC recognizes what your data is — dictionaries and patterns that classify, tag, and prepare every column and document for governance.",
       meta=[("Primary role", "Business Analyst"), ("Estimated time", "60 minutes"), ("Dataset", DS)],
       header="Workshop 5: Data Identification")),
]

# Optional filters: `python tools/build-docx.py Workshop-03` builds only docs
# whose markdown path contains one of the arguments.
import sys
FILTERS = sys.argv[1:]

for md, out, cfg in DOCS:
    if FILTERS and not any(f in md for f in FILTERS):
        continue
    d = convert(os.path.join(CW, md), cfg)
    build(os.path.join(CW, out), d, cfg)
    print("built", out, "| steps-lists:", len(d.numids), "| images:", [n for _, n, _ in d.images])
print("ALL BUILT (RETAIL)" + (" (filtered: %s)" % ",".join(FILTERS) if FILTERS else ""))
