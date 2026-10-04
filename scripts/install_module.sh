#!/bin/bash
# CONCORDE — installation du module Odoo 17 (a executer en root apres un git pull)
set -e
cd /opt/concorde
MODULE_DIR=deploy/addons/concorde

# Copie fidele du moteur depuis le depot local (jamais de transcription manuelle)
mkdir -p "$MODULE_DIR/engine"
cp core/*.py "$MODULE_DIR/engine/"
cp mapping_quadra_odoo.json "$MODULE_DIR/engine/"

# Logo officiel CONCORDE (SVG, copie exacte du fichier fourni par MASITH,
# tatouage numerique invisible inclus) dans le module
mkdir -p "$MODULE_DIR/static/description"
cat > "$MODULE_DIR/static/description/logo.svg" <<'SVGEOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 200" width="560" height="200">
  <!-- ================================================================
       TATOUAGE NUMÉRIQUE INVISIBLE — propriété intellectuelle
       © MASITH — Stéphane Moreau — reproduction non autorisée interdite
       Trois marqueurs invisibles à l'œil nu, lisibles par machine :
       1. <metadata> déclaratif (lisible par tout parseur XML/IA)
       2. textes fantômes opacité 0.003 (imperceptibles)
       3. rangée de micro-points codés (rayon 0.3, opacité 0.02)
       Tout SVG contenant ces marqueurs = copie du logo officiel MASITH.
       ================================================================ -->
  <title>CONCORDE — Liaison comptable universelle</title>
  <metadata id="wm-meta">PROPRIETAIRE: MASITH | AUTEUR: Stephane Moreau |
    TATOUAGE: concorde-logo-v1 | ANNEE: 2026 | USAGE: reproduction interdite
    sans autorisation ecrite de MASITH</metadata>

  <!-- Symbole : balance comptable stylisée (bordeaux et or) -->
  <g transform="translate(58,100)">
    <rect x="-4" y="-58" width="8" height="96" rx="4" fill="#8B1E3F"/>
    <rect x="-52" y="-66" width="104" height="8" rx="4" fill="#8B1E3F"/>
    <line x1="-52" y1="-58" x2="-52" y2="-30" stroke="#D4A017" stroke-width="4"/>
    <line x1="52" y1="-58" x2="52" y2="-30" stroke="#D4A017" stroke-width="4"/>
    <path d="M-76,-30 A26,14 0 0 0 -28,-30 Z" fill="#D4A017"/>
    <path d="M28,-30 A26,14 0 0 0 76,-30 Z" fill="#D4A017"/>
    <rect x="-30" y="36" width="60" height="10" rx="5" fill="#8B1E3F"/>
    <circle cx="0" cy="-74" r="9" fill="#D4A017" stroke="#8B1E3F" stroke-width="3"/>
  </g>

  <!-- Typographie -->
  <text x="160" y="112" font-family="Georgia, 'Times New Roman', serif"
        font-size="64" font-weight="bold" letter-spacing="3" fill="#8B1E3F">CONCORDE</text>
  <text x="162" y="142" font-family="Verdana, sans-serif" font-size="15"
        letter-spacing="4" fill="#B06A2E">LIAISON COMPTABLE · AU CENTIME PRÈS</text>
  <text x="163" y="168" font-family="Verdana, sans-serif" font-size="12"
        fill="#6B4F3A">MARQUÉ DÉPOSÉ ™</text>

  <!-- MARQUEUR 2 : textes fantômes (opacité 0.3 % — invisible à l'œil nu,
       détectable par analyse des attributs ou extraction du texte) -->
  <text x="14" y="196" font-size="1.2" opacity="0.003"
        fill="#8B1E3F">MASITH-Stephane-Moreau-tatouage-1</text>
  <text x="300" y="8" font-size="1.2" opacity="0.003"
        fill="#D4A017">MASITH-Stephane-Moreau-tatouage-2</text>
  <text x="278" y="196" font-size="1.2" opacity="0.003"
        fill="#8B1E3F">MASITH-Stephane-Moreau-tatouage-3</text>

  <!-- MARQUEUR 3 : rangée de micro-points codés (r=0.3, opacité 2 %).
       Les décimales des abscisses encodent MASITH-STEPHANE MOREAU
       (dernière décimale = ordre ASCII modulo 10) : présence d'une
       rangée de 20+ micro-points alignés = signature de copie. -->
  <g opacity="0.02" fill="#8B1E3F">
    <circle cx="20.07" cy="193" r="0.3"/><circle cx="30.05" cy="193" r="0.3"/>
    <circle cx="40.03" cy="193" r="0.3"/><circle cx="50.03" cy="193" r="0.3"/>
    <circle cx="60.04" cy="193" r="0.3"/><circle cx="70.02" cy="193" r="0.3"/>
    <circle cx="80.05" cy="193" r="0.3"/><circle cx="90.09" cy="193" r="0.3"/>
    <circle cx="100.00" cy="193" r="0.3"/><circle cx="110.02" cy="193" r="0.3"/>
    <circle cx="120.05" cy="193" r="0.3"/><circle cx="130.08" cy="193" r="0.3"/>
    <circle cx="140.09" cy="193" r="0.3"/><circle cx="150.02" cy="193" r="0.3"/>
    <circle cx="160.07" cy="193" r="0.3"/><circle cx="170.09" cy="193" r="0.3"/>
    <circle cx="180.02" cy="193" r="0.3"/><circle cx="190.09" cy="193" r="0.3"/>
    <circle cx="200.05" cy="193" r="0.3"/><circle cx="210.05" cy="193" r="0.3"/>
  </g>
</svg>
SVGEOF
# copie exacte : retirer le retour a la ligne final ajoute par le heredoc
truncate -s -1 "$MODULE_DIR/static/description/logo.svg"

# Icone du module : balance bordeaux/or, rendu fidele aux coordonnees du logo SVG
python3 - "$MODULE_DIR/static/description/icon.png" <<'PYEOF'
import sys
import struct, zlib, math

BORDEAUX = (139, 30, 63)
OR = (212, 160, 23)
SS = 8
S = 256
W = S * SS
SYMX0, SYMX1 = 6, 110
SYMY0, SYMY1 = 12, 148
SW, SH = SYMX1 - SYMX0, SYMY1 - SYMY0
px = [[(0, 0, 0, 0)] * W for _ in range(W)]

def svg(x, y):
    return (x - SYMX0) / SW * W, (y - SYMY0) / SH * W

def put(x, y, col):
    if 0 <= x < W and 0 <= y < W:
        px[y][x] = col + (255,)

def rect(x, y, w, h, rx, col):
    x0, y0 = svg(x, y)
    x1, y1 = svg(x + w, y + h)
    rr = rx / SW * W
    for yy in range(max(0, int(y0)), min(W, int(y1) + 1)):
        for xx in range(max(0, int(x0)), min(W, int(x1) + 1)):
            inside = True
            dxl = xx - (x0 + rr); dxr = (x1 - rr) - xx
            dyt = yy - (y0 + rr); dyb = (y1 - rr) - yy
            if dxl < 0 and dyt < 0 and math.hypot(xx-(x0+rr), yy-(y0+rr)) > rr: inside = False
            elif dxr < 0 and dyt < 0 and math.hypot(xx-(x1-rr), yy-(y0+rr)) > rr: inside = False
            elif dxl < 0 and dyb < 0 and math.hypot(xx-(x0+rr), yy-(y1-rr)) > rr: inside = False
            elif dxr < 0 and dyb < 0 and math.hypot(xx-(x1-rr), yy-(y1-rr)) > rr: inside = False
            if inside: put(xx, yy, col)

def ligne(x1, y1, x2, y2, ep, col):
    xa, ya = svg(x1, y1); xb, yb = svg(x2, y2)
    e = ep / SW * W / 2.0
    n = int(max(abs(xb-xa), abs(yb-ya))) * 2 + 1
    for i in range(n+1):
        xx = xa + (xb-xa)*i/n; yy = ya + (yb-ya)*i/n
        for ox in range(int(-e-1), int(e+2)):
            for oy in range(int(-e-1), int(e+2)):
                if ox*ox+oy*oy <= e*e: put(int(xx)+ox, int(yy)+oy, col)

def demi_ellipse(cx, cy, rx, ry, col):
    x0, y0 = svg(cx - rx, cy)
    x1, _ = svg(cx + rx, cy)
    rr_x = rx / SW * W; rr_y = ry / SH * W
    ymin = int(max(0, y0)); ymax = int(min(W, y0 + rr_y + 2))
    cxp = (x0 + x1) / 2
    for yy in range(ymin, ymax):
        for xx in range(W):
            dx = (xx - cxp) / rr_x
            dy = (yy - y0) / rr_y
            if 0 <= dy <= 1 and dx*dx + dy*dy <= 1: put(xx, yy, col)

def cercle(cx, cy, r, ep, col_fill, col_stroke):
    xc, yc = svg(cx, cy)
    rr = r / SW * W; e = ep / SW * W / 2
    for yy in range(int(yc-rr-e-1), int(yc+rr+e+2)):
        if yy < 0 or yy >= W: continue
        for xx in range(int(xc-rr-e-1), int(xc+rr+e+2)):
            if xx < 0 or xx >= W: continue
            d = math.hypot(xx-xc, yy-yc)
            if abs(d-rr) <= e: put(xx, yy, col_stroke)
            elif d < rr: put(xx, yy, col_fill)

T = (58, 100)
def tx(x, y): return (x + T[0], y + T[1])

X, Y = tx(-4, -58); rect(X, Y, 8, 96, 4, BORDEAUX)
X, Y = tx(-52, -66); rect(X, Y, 104, 8, 4, BORDEAUX)
ligne(tx(-52, -58)[0], tx(-52, -58)[1], tx(-52, -30)[0], tx(-52, -30)[1], 4, OR)
ligne(tx(52, -58)[0], tx(52, -58)[1], tx(52, -30)[0], tx(52, -30)[1], 4, OR)
X, Y = tx(-52, -30); demi_ellipse(X, Y, 24, 14, OR)
X, Y = tx(28, -30); demi_ellipse(X, Y, 24, 14, OR)
X, Y = tx(-30, 36); rect(X, Y, 60, 10, 5, BORDEAUX)
X, Y = tx(0, -74); cercle(X, Y, 9, 3, OR, BORDEAUX)

def png(path, w, h, pixels):
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''
    for y in range(h):
        raw += b'\x00' + b''.join(bytes(pixels[y][x]) for x in range(w))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b''))

out = [[None]*S for _ in range(S)]
for y in range(S):
    for x in range(S):
        r = g = b = a = 0
        for sy in range(SS):
            for sx in range(SS):
                pr, pg, pb, pa = px[y*SS+sy][x*SS+sx]
                r += pr*pa; g += pg*pa; b += pb*pa; a += pa
        if a == 0:
            out[y][x] = (0, 0, 0, 0)
        else:
            out[y][x] = (min(255, r//a), min(255, g//a), min(255, b//a), a//(SS*SS))
png(sys.argv[1], S, S, out)
PYEOF

# Installation du module dans la base concorde
cd deploy
docker compose run --rm odoo -u concorde -d concorde --without-demo=all --stop-after-init
docker compose up -d
echo "=== MODULE CONCORDE INSTALLE ==="
