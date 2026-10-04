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

# Icone du module : balance comptable bordeaux/or generee par code (fond transparent)
python3 - "$MODULE_DIR/static/description/icon.png" <<'PYEOF'
import sys, struct, zlib, math

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

BORDEAUX = (139, 30, 63)
OR = (212, 160, 23)
SS = 4
S = 128
W = S * SS
px = [[(0, 0, 0, 0)] * W for _ in range(W)]

def put(x, y, col):
    if 0 <= x < W and 0 <= y < W:
        px[y][x] = col + (255,)

def rect(x0, y0, x1, y1, col):
    for yy in range(int(y0*W), int(y1*W)+1):
        for xx in range(int(x0*W), int(x1*W)+1):
            put(xx, yy, col)

def line(x0, y0, x1, y1, col, ep):
    x0, y0, x1, y1 = x0*W, y0*W, x1*W, y1*W
    dx, dy = x1-x0, y1-y0
    n = int(max(abs(dx), abs(dy)))*2+1
    for i in range(n+1):
        xx = x0 + dx*i/n
        yy = y0 + dy*i/n
        for ox in range(-ep, ep+1):
            for oy in range(-ep, ep+1):
                if ox*ox+oy*oy <= ep*ep:
                    put(int(xx)+ox, int(yy)+oy, col)

def pan(cx, cy, rx, ry, col):
    for yy in range(W):
        for xx in range(W):
            dx = (xx/SS - cx)/rx
            dy = (yy/SS - cy)/ry
            if 0 <= dy <= 1 and dx*dx + dy*dy <= 1:
                put(xx, yy, col)

def circle(cx, cy, r, col, stroke=0):
    for yy in range(W):
        for xx in range(W):
            d = math.hypot(xx/SS-cx, yy/SS-cy)
            if abs(d-r) <= stroke or (stroke == 0 and d <= r):
                put(xx, yy, col)

rect(0.47, 0.06, 0.53, 0.55, BORDEAUX)
rect(0.20, 0.14, 0.80, 0.21, BORDEAUX)
line(0.24, 0.21, 0.24, 0.44, OR, SS//2)
line(0.76, 0.21, 0.76, 0.44, OR, SS//2)
pan(0.24, 0.44, 0.16, 0.11, OR)
pan(0.76, 0.44, 0.16, 0.11, OR)
rect(0.35, 0.55, 0.65, 0.62, BORDEAUX)
circle(0.5, 0.075, 0.055, OR, SS//2)

out = [[None]*S for _ in range(S)]
for y in range(S):
    for x in range(S):
        r = g = b = a = 0
        for sy in range(SS):
            for sx in range(SS):
                pr, pg, pb, pa = px[y*SS+sy][x*SS+sx]
                r += pr*pa
                g += pg*pa
                b += pb*pa
                a += pa
        if a == 0:
            out[y][x] = (0, 0, 0, 0)
        else:
            out[y][x] = (min(255, r//a), min(255, g//a), min(255, b//a), a//(SS*SS))
png(sys.argv[1], S, S, out)
print('icon.png generee (balance bordeaux/or, fond transparent)')

PYEOF

# Installation du module dans la base concorde
cd deploy
docker compose run --rm odoo -i concorde -d concorde --without-demo=all --stop-after-init
docker compose up -d
echo "=== MODULE CONCORDE INSTALLE ==="
