#!/bin/bash
# CONCORDE — installation du module Odoo 17 (a executer en root apres un git pull)
set -e
cd /opt/concorde
MODULE_DIR=deploy/addons/concorde

# Copie fidele du moteur depuis le depot local (jamais de transcription manuelle)
mkdir -p "$MODULE_DIR/engine"
cp core/*.py "$MODULE_DIR/engine/"
cp mapping_quadra_odoo.json "$MODULE_DIR/engine/"

# Icone du module (generee par code : arche du pont de la Concorde sur fond bleu nuit)
mkdir -p "$MODULE_DIR/static/description"
python3 - "$MODULE_DIR/static/description/icon.png" <<'PYEOF'
import sys, struct, zlib, math

def png(path, w, h, pixels):
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''
    for y in range(h):
        raw += b'\x00' + b''.join(bytes(pixels[y][x]) for x in range(w))
    data = (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))
    open(path, 'wb').write(data)

S = 256
px = [[None]*S for _ in range(S)]
for y in range(S):
    for x in range(S):
        t = y / S
        r = int(10 + 14*t); g = int(24 + 48*t); b = int(48 + 88*t)
        cy, cx = 150, 128
        in_band = 118 <= y <= 134
        d = math.hypot(x - cx, y - cy)
        in_arc = abs(d - 66) <= 9 and y <= cy
        in_pier = (68 <= y <= 210) and ((52 <= x <= 72) or (184 <= x <= 204))
        if in_band or in_arc or in_pier:
            r, g, b = 245, 249, 255
        if y > 216 and (x + y) % 9 < 3:
            r = int(r*0.7); g = int(g*0.85); b = min(255, b+40)
        px[y][x] = (r, g, b, 255)
png(sys.argv[1], S, S, px)
print('icon.png generee')
PYEOF

# Installation du module dans la base concorde
cd deploy
docker compose run --rm odoo -i concorde -d concorde --without-demo=all --stop-after-init
docker compose up -d
echo "=== MODULE CONCORDE INSTALLE ==="
