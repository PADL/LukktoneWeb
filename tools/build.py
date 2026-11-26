#!/usr/bin/env python3
"""Build the static site from the Lukktone Website Design's page sources.

The Claude Design canvas "Lukktone Website" is the source of truth. Its
artboards are saved in design/*.dc.html; this script turns them into plain
HTML pages at the repo root, with images served from images/.

    python3 tools/build.py            # staging build (noindex)
    python3 tools/build.py --public   # production build (indexable)

Image references in the Design (/_blob/<id>) are mapped to files in images/
through design/blobs.json. A new image in the Design needs its file added to
images/ and an entry in that map.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"

PAGES = {
    "MonitorTwo.dc.html": "index.html",
    "RouterOne.dc.html": "router-one.html",
    "Main.dc.html": "ocacon.html",
}
LINKS = {"MonitorTwo.dc.html": "./", "RouterOne.dc.html": "router-one.html", "Main.dc.html": "ocacon.html"}
FONT = '<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600&display=swap" rel="stylesheet">'

CAROUSEL_JS = """(()=>{const t=document.getElementById('track');if(!t)return;const s=t.children,d=[...document.querySelectorAll('.dot')],on=%r,off=%r;let i=0;const go=n=>{i=(n+s.length)%%s.length;t.style.transform=`translateX(-${i*100}%%)`;[...s].forEach((el,k)=>el.setAttribute('aria-hidden',k!==i));d.forEach((b,k)=>{b.setAttribute('aria-current',k===i);b.style.cssText=k===i?on:off})};document.getElementById('prev').onclick=()=>go(i-1);document.getElementById('next').onclick=()=>go(i+1);d.forEach((b,k)=>b.onclick=()=>go(k));go(0)})();"""
FORM_JS = """document.getElementById('form').addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target),o=f.get('organisation'),s=encodeURIComponent(%r+(o?' — '+o:'')),b=encodeURIComponent(['Name: '+f.get('name'),'Email: '+f.get('email'),'Organisation: '+(o||'—'),'Application: '+(f.get('application')||'—'),'',f.get('message')||''].join('\\n'));location.href=`mailto:hello@lukktone.com?subject=${s}&body=${b}`});"""


def fail(msg):
    sys.exit(f"build: {msg}")


def blob_to_file(m, blobs, page):
    bid = m.group(1)
    if bid not in blobs:
        fail(f"{page}: image /_blob/{bid} is not in design/blobs.json; add its file to images/ and map it")
    return "images/" + blobs[bid]


def build(src, public, blobs):
    text = (DESIGN / src).read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", text, re.S).group(1)
    style = re.search(r"<helmet>\s*<style>(.*?)</style>\s*</helmet>", text, re.S).group(1).strip()
    body = re.search(r"</helmet>(.*)</x-dc>", text, re.S).group(1).strip()
    script = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', text, re.S).group(1)

    # Carousel: expand the slide and dot loops from the shots listed in the script.
    shots = re.findall(r"src: '(/_blob/[0-9a-f]+)', alt: '((?:[^'\\]|\\.)*)'", script)
    base = re.search(r"var base = '([^']*)'", script)
    if "{{slides}}" in body:
        n = len(shots)
        if not n or not base:
            fail(f"{src}: carousel found but no shots or dot style in its script")
        on = base.group(1) + "#111; color: #111;"
        off = base.group(1) + "transparent; color: #444;"

        def slides(m):
            tpl = m.group(1)
            out = []
            for k, (s, a) in enumerate(shots):
                out.append(tpl.replace("{{s.src}}", s).replace("{{s.alt}}", html.escape(a.replace("\\'", "'"), quote=True))
                           .replace("{{s.label}}", f"{k + 1} of {n}").replace("{{s.hidden}}", "false" if k == 0 else "true"))
            return "".join(out)

        def dots(m):
            tpl = m.group(1)
            out = []
            for k in range(n):
                out.append(tpl.replace('onClick="{{d.pick}}"', 'class="dot"').replace("{{d.current}}", "true" if k == 0 else "false")
                           .replace("{{d.aria}}", f"Show image {k + 1}").replace("{{d.style}}", on if k == 0 else off)
                           .replace("{{d.num}}", f"{k + 1:02d}"))
            return "".join(out)

        body = re.sub(r'<sc-for list="\{\{slides\}\}"[^>]*>(.*?)</sc-for>', slides, body, flags=re.S)
        body = re.sub(r'<sc-for list="\{\{dots\}\}"[^>]*>(.*?)</sc-for>', dots, body, flags=re.S)
        body = body.replace('style="{{trackStyle}}"', 'id="track" style="display: flex; transition: transform .7s cubic-bezier(.6,0,.2,1);"')
        body = body.replace('onClick="{{prev}}"', 'id="prev"').replace('onClick="{{next}}"', 'id="next"')
    else:
        on = off = ""

    body = body.replace('open="{{yes}}"', "open").replace('required="{{yes}}"', "required")
    body = body.replace('onSubmit="{{send}}"', 'id="form"')
    for dc, url in LINKS.items():
        body = body.replace(f'href="{dc}"', f'href="{url}"')
    body = re.sub(r"/_blob/([0-9a-f]+)", lambda m: blob_to_file(m, blobs, src), body)

    left = re.findall(r"\{\{[^}]*\}\}|<sc-[a-z]+|<dc-import|<x-import", body)
    if left:
        fail(f"{src}: unsupported template parts left after conversion: {sorted(set(left))}")

    subject = re.search(r"encodeURIComponent\('([^']*) enquiry'", script)
    js = []
    if 'id="track"' in body:
        js.append(CAROUSEL_JS % (on, off))
    if 'id="form"' in body:
        js.append(FORM_JS % ((subject.group(1) if subject else "Lukktone") + " enquiry"))

    robots = "" if public else '<meta name="robots" content="noindex, nofollow">\n'
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n{robots}'
            f"<title>{title}</title>\n{FONT}\n<style>\n{style}\n</style>\n</head>\n<body>\n"
            f"<!-- Generated by tools/build.py from design/{src}. Edit the Design, not this file. -->\n"
            f"{body}\n<script>\n" + "\n".join(js) + "\n</script>\n</body>\n</html>\n")


def main():
    public = "--public" in sys.argv[1:]
    blobs = json.loads((DESIGN / "blobs.json").read_text())
    for src, out in PAGES.items():
        (ROOT / out).write_text(build(src, public, blobs), encoding="utf-8")
        print(f"design/{src} -> {out}")


if __name__ == "__main__":
    main()
