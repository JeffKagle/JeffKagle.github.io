"""'Above & Below the Waterline' scene for the portfolio cover (table of contents) and chapter thumbnails.

Below the waterline: an anatomical fish; each biology label links to a related chapter.
Above it: a sailboat (tiller, engine) and a sailor wearing the wearable devices.
Chapter numbers come from the portfolio order; edit SCENE to re-map parts to projects.
"""
import math
from html import escape as esc

SEA, SEAL, WEED, WEEDL, INK, MID, GREY, CORAL = '#1F6F8B', '#A9D2E0', '#3E7C4F', '#DCEFE2', '#1A1A1A', '#6B7280', '#C9D1D8', '#E07A5F'
CY, WL = 640, 420
NOW = 'current-research'

# part -> what the label says and which chapter it points to
SCENE = {
    'muscle':  {'id': 'hasel-rotary-actuator', 'kicker': 'MYOMERES · MUSCLE', 'short': 'Liquid DEA Motor',
                'desc': 'Fish swim by contracting blocks of muscle in a wave from head to tail.',
                'thumb': ('INSPIRED BY: MYOMERES', 'blocks of muscle that contract in a wave to drive swimming')},
    'fins':    {'id': 'cuttlefish-hybrid-model', 'kicker': 'FINS · LOCOMOTION', 'short': 'Cuttlefish Fin Model',
                'desc': 'Fins bend and ripple to push water; cuttlefish swim with one long rippling fin.',
                'thumb': ('INSPIRED BY: RIPPLING FINS', 'fins that bend and ripple to push water')},
    'lateral': {'id': NOW, 'kicker': 'LATERAL LINE · HEARING', 'short': 'Underwater Acoustics',
                'desc': 'Rows of pressure sensors along each side let fish feel sound and vibration.'},
    'heart':   {'id': NOW, 'kicker': 'HEART & BLOOD · ENERGY', 'short': 'Embodied Energy',
                'desc': 'Blood carries fuel to every muscle, so energy is stored throughout the body.'},
    'sailor':  {'items': [('snap-through-actuator', 'Snap-Through Haptics'), ('gait-coach', 'The Gait Coach'),
                          ('focus-glasses', 'Focus Glasses')],
                'kicker': 'THE SAILOR · WEARABLES', 'desc': 'Devices for the human body:',
                'thumb': ('ABOVE THE WATERLINE', 'a wearable device for the human body')},
    'tiller':  {'id': 'ancore-tiller-extension', 'kicker': 'TILLER EXTENSION', 'short': 'ANCORE U Tiller Joint',
                'thumb': ('ABOVE THE WATERLINE', 'the tiller that steers the boat')},
    'engine':  {'id': 'inline-3-engine', 'kicker': 'ENGINE', 'short': 'TR315-r Inline-3 Engine',
                'thumb': ('ABOVE THE WATERLINE', 'the engine that drives the boat')},
}


def part_of(project_id):
    for part, v in SCENE.items():
        if v.get('id') == project_id or any(pid == project_id for pid, _ in v.get('items', [])):
            return part
    return None


def scene_ids():
    ids = set()
    for v in SCENE.values():
        if v.get('id') and v['id'] != NOW:
            ids.add(v['id'])
        ids.update(pid for pid, _ in v.get('items', []))
    return ids


# ───────── geometry ─────────
def cr(points, closed=False):
    pts = points[:]
    pts = ([pts[-1]] + pts + [pts[0], pts[1]]) if closed else ([pts[0]] + pts + [pts[-1]])
    d = f'M{pts[1][0]:.1f},{pts[1][1]:.1f}'
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f' C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}'
    return d + (' Z' if closed else '')


UPPER = [(170, 645), (180, 628), (205, 606), (245, 588), (300, 575), (360, 570), (430, 574), (500, 590), (560, 612), (605, 628)]
LOWER = [(605, 650), (560, 662), (500, 682), (430, 698), (360, 704), (300, 700), (245, 690), (205, 676), (180, 662)]
BODY = cr(UPPER + LOWER, closed=True)


def interp(pts, x):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if min(x0, x1) <= x <= max(x0, x1):
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return pts[-1][1]


up = lambda x: interp(UPPER, x)
lo = lambda x: interp(list(reversed(LOWER)) + [(605, 650)], x)


def waterline(y0, x0, x1):
    pts = ' '.join(f'L{x},{y0 + 3 * math.sin(x / 22):.1f}' for x in range(x0, x1 + 1, 6))
    return f'M{x0},{y0} {pts}'


def fish(uid, hl=None):
    c = lambda part, col: col if (hl is None or hl == part) else GREY
    line = INK if hl is None else '#B8C2CA'
    fin, fins = ('#E4EEF2', '#5B7A88') if hl is None else ('#F0F3F5', '#C3CCD3')
    o = [f'''<defs><linearGradient id="skin-{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{'#B9D2DD' if hl is None else '#E4EAEE'}"/><stop offset=".55" stop-color="#EAF2F5"/><stop offset="1" stop-color="#FBFDFE"/></linearGradient>
<pattern id="scales-{uid}" width="12" height="8" patternUnits="userSpaceOnUse"><path d="M0,8 Q6,0 12,8" fill="none" stroke="#9FB8C4" stroke-width=".7"/></pattern>
<clipPath id="body-{uid}"><path d="{BODY}"/></clipPath></defs>''']
    o.append(f'<path d="M304,576 C312,546 326,526 348,520 C372,516 398,528 416,556 L424,574 Z" fill="{fin}" stroke="{fins}" stroke-width="1.3"/>')
    for x, y in ((318, 540), (334, 527), (352, 520), (372, 520), (392, 528), (408, 544)):
        o.append(f'<line x1="{x}" y1="{y}" x2="{x+3}" y2="{up(x+3)+2:.0f}" stroke="{fins}" stroke-width=".8"/>')
    o.append(f'<path d="M432,575 Q448,536 492,540 Q512,556 522,596 Z" fill="{fin}" stroke="{fins}" stroke-width="1.3"/>')
    o.append(f'<path d="M605,628 C640,610 668,582 706,560 Q682,602 670,640 Q682,680 706,722 C668,700 640,670 605,652 Z" fill="{fin}" stroke="{fins}" stroke-width="1.4"/>')
    for k in range(7):
        a = -0.5 + k / 6
        o.append(f'<line x1="612" y1="{640+a*14:.0f}" x2="{690+abs(a)*8:.0f}" y2="{640+a*150:.0f}" stroke="{fins}" stroke-width=".6" opacity=".7"/>')
    af, afs = c('fins', WEEDL), c('fins', WEED)
    o.append(f'<path d="M468,694 C478,716 498,728 522,726 C538,716 548,694 552,668 Z" fill="{af}" stroke="{afs}" stroke-width="1.5"/>')
    for k in range(5):
        x = 476 + k * 15
        o.append(f'<line x1="{x}" y1="{lo(x)-1:.0f}" x2="{x+6}" y2="{min(726, lo(x)+30-k*3):.0f}" stroke="{afs}" stroke-width=".8" opacity=".7"/>')
    o.append(f'<path d="M326,702 Q336,726 360,734 Q356,716 350,704 Z" fill="{af}" stroke="{afs}" stroke-width="1.3"/>')
    o.append(f'<path d="{BODY}" fill="url(#skin-{uid})" stroke="{line}" stroke-width="1.7"/>')
    o.append(f'<rect x="262" y="560" width="350" height="150" fill="url(#scales-{uid})" opacity="{0.45 if hl is None else 0.2}" clip-path="url(#body-{uid})"/>')
    mc = c('muscle', SEA)
    for x in range(304, 600, 24):
        t, b = up(x) + 4, lo(x) - 4
        o.append(f'<polyline points="{x},{t:.0f} {x-9},{CY-22} {x+5},{CY-2} {x-9},{CY+20} {x},{b:.0f}" fill="none" stroke="{mc}" stroke-width="1.35" opacity="{0.6 if hl is None else (0.9 if hl == "muscle" else 0.5)}"/>')
    o.append(f'<path d="M258,594 Q284,640 252,688" fill="none" stroke="{line}" stroke-width="1.5"/>')
    o.append(f'<path d="M171,646 Q182,652 192,650" fill="none" stroke="{line}" stroke-width="1.4"/>')
    o.append(f'<circle cx="208" cy="626" r="9.5" fill="#fff" stroke="{line}" stroke-width="1.4"/><circle cx="206" cy="626" r="5" fill="{line}"/><circle cx="204.5" cy="624.5" r="1.4" fill="#fff"/>')
    o.append(f'<path d="M282,648 Q318,636 350,656 Q320,672 284,658 Z" fill="{fin}" stroke="{fins}" stroke-width="1.3"/>')
    for k in range(4):
        o.append(f'<line x1="285" y1="652" x2="{335+k*4}" y2="{647+k*6}" stroke="{fins}" stroke-width=".7"/>')
    lc = c('lateral', WEED)
    ll = [(262, 612), (320, 606), (380, 604), (440, 607), (500, 614), (560, 626), (600, 636)]
    o.append(f'<path d="{cr(ll)}" fill="none" stroke="{lc}" stroke-width="1.4" stroke-dasharray="5 4"/>')
    for k in range(14):
        x = 268 + k * 24
        o.append(f'<circle cx="{x}" cy="{interp(ll, x):.1f}" r="2.1" fill="{lc}"/>')
    ec = c('heart', WEED)
    o.append(f'<path d="M266,688 C254,680 252,668 261,666 C265,665 267,668 268,670 C270,666 274,664 278,667 C284,672 278,682 266,688 Z" fill="{ec}" fill-opacity=".18" stroke="{ec}" stroke-width="1.5" stroke-dasharray="3 2.5"/>')
    o.append(f'<path d="M272,668 C300,646 360,634 600,638" fill="none" stroke="{ec}" stroke-width="1.6" stroke-dasharray="6 4"/>')
    return ''.join(o)


def boat(hl=None):
    c = lambda part, col: col if (hl is None or hl == part) else GREY
    rig = '#4B5563' if hl is None else '#B8C2CA'
    o = [f'<line x1="395" y1="398" x2="395" y2="262" stroke="{rig}" stroke-width="2.4"/>',
         f'<path d="M397,266 L397,378 L488,378 Z" fill="#fff" stroke="{rig}" stroke-width="1.4"/>',
         f'<line x1="395" y1="381" x2="492" y2="381" stroke="{rig}" stroke-width="2.4"/>',
         f'<path d="M392,272 L308,394 L392,394 Z" fill="#fff" stroke="{rig}" stroke-width="1.4"/>',
         f'<path d="M294,396 L542,396 L538,424 Q430,440 330,425 Z" fill="#fff" stroke="{INK if hl is None else "#B8C2CA"}" stroke-width="1.7"/>',
         f'<line x1="300" y1="404" x2="538" y2="404" stroke="{SEA if hl is None else GREY}" stroke-width="2.2"/>',
         f'<path d="M420,434 L432,474 L452,474 L446,436 Z" fill="#E5E9EC" stroke="{rig}" stroke-width="1.2"/>',
         f'<path d="M533,412 L540,456 L548,456 L544,412 Z" fill="#E5E9EC" stroke="{rig}" stroke-width="1.2"/>']
    ec = c('engine', SEA)  # outboard: cowling, leg, cavitation plate, propeller
    o.append(f'<path d="M546,388 Q546,380 556,380 L566,380 Q572,380 572,388 L572,400 Q572,404 566,404 L550,404 Q546,404 546,400 Z" fill="{ec}"/>')
    o.append(f'<path d="M553,404 L561,404 L560,446 L554,446 Z" fill="{ec}"/><rect x="549" y="430" width="16" height="3" rx="1" fill="{ec}"/>')
    o.append(f'<ellipse cx="557" cy="448" rx="3" ry="7" fill="{ec}"/><ellipse cx="557" cy="448" rx="7" ry="2.2" fill="{ec}" opacity=".7"/>')
    tc = c('tiller', SEA)
    o.append(f'<line x1="540" y1="397" x2="528" y2="390" stroke="{rig}" stroke-width="3" stroke-linecap="round"/>')
    o.append(f'<line x1="528" y1="390" x2="505" y2="372" stroke="{tc}" stroke-width="3" stroke-linecap="round"/><circle cx="528" cy="390" r="3.2" fill="{tc}"/>')
    sk, vest, gear = c('sailor', '#2B3138'), c('sailor', CORAL), c('sailor', SEA)  # sailor: seated, life vest, glasses, haptic band
    o.append(f'<path d="M517,392 L498,394 L496,396" fill="none" stroke="{sk}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>')
    o.append(f'<path d="M507,360 Q515,356 523,360 L522,388 Q515,392 508,388 Z" fill="{vest}"/>')
    o.append(f'<path d="M510,366 L503,374" stroke="{sk}" stroke-width="3" stroke-linecap="round"/>')
    o.append(f'<rect x="503" y="368" width="6" height="5" rx="1" fill="{gear}" transform="rotate(-42 506 370)"/>')
    o.append(f'<circle cx="515" cy="348" r="8" fill="#F7EFE8" stroke="{sk}" stroke-width="1.5"/>')
    o.append(f'<path d="M507,345 Q515,337 523,345" fill="{sk}"/>')
    o.append(f'<circle cx="509.5" cy="349" r="2.7" fill="none" stroke="{gear}" stroke-width="1.3"/><line x1="512.2" y1="349" x2="515.5" y2="349" stroke="{gear}" stroke-width="1.1"/>')
    return ''.join(o)


def wrap(text, n):
    words, lines, cur = text.split(), [], ''
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur); cur = w
        else:
            cur = (cur + ' ' + w).strip()
    return lines + [cur]


def label(x, y, badge, kicker, desc, chapter, target, href=None, items=None, w=36, start=None):
    o = []
    bx, by = x + 14, y
    now = badge == 'NOW'
    sy = by + 14 if target[1] > by else by - 14
    sx, sy = start if start else (bx, sy)
    o.append(f'<path d="M{sx},{sy} L{target[0]},{target[1]}" stroke="#8C97A1" stroke-width="1.2"/>')
    o.append(f'<circle cx="{target[0]}" cy="{target[1]}" r="3.6" fill="#fff" stroke="#4B5563" stroke-width="1.4"/>')
    if now:
        o.append(f'<circle cx="{bx}" cy="{by}" r="14" fill="#fff" stroke="{WEED}" stroke-width="2" stroke-dasharray="4 3"/><text x="{bx}" y="{by+3.5}" font-size="8.5" font-weight="600" fill="{WEED}" text-anchor="middle">NOW</text>')
    elif badge:
        o.append(f'<circle cx="{bx}" cy="{by}" r="14" fill="{SEA}"/><text x="{bx}" y="{by+4.5}" style="font-family:Caudex,serif" font-weight="700" font-size="12.5" fill="#fff" text-anchor="middle">{badge}</text>')
    else:
        o.append(f'<circle cx="{bx}" cy="{by}" r="14" fill="#fff" stroke="{SEA}" stroke-width="2"/><circle cx="{bx}" cy="{by}" r="4" fill="{SEA}"/>')
    ty = by - 2
    o.append(f'<text x="{x+36}" y="{ty}" font-size="10" font-weight="600" letter-spacing="1.3" fill="{WEED}">{esc(kicker)}</text>')
    ty += 17
    for ln in (wrap(desc, w) if desc else []):
        o.append(f'<text x="{x+36}" y="{ty}" font-size="12.2" fill="#4B5563">{esc(ln)}</text>'); ty += 15.5
    for it_href, it_text in (items or []):
        o.append(f'<a href="{it_href}"><text x="{x+36}" y="{ty+1}" style="font-family:Caudex,serif" font-weight="700" font-size="13.5" fill="{INK}">{esc(it_text)}</text></a>'); ty += 17
    if chapter:
        style = 'font-style:italic' if now else 'font-family:Caudex,serif'
        o.append(f'<text x="{x+36}" y="{ty+2}" style="{style}" font-weight="{400 if now else 700}" font-size="{12.5 if now else 13.5}" fill="{WEED if now else INK}">{esc(chapter)}</text>')
    body = ''.join(o)
    return f'<a href="{href}">{body}</a>' if href and not items else body


def cover_svg(nums):
    """nums: project id -> chapter number string ('01'...)."""
    T = lambda x, y: (round(0.85 * x + 5), round(0.85 * y + 106))
    s = ['<defs><linearGradient id="water-cover" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E3F0F5"/><stop offset="1" stop-color="#CFE3EB"/></linearGradient>'
         '<clipPath id="scene-cover"><rect x="30" y="246" width="790" height="640" rx="14"/></clipPath></defs>']
    sc = ['<rect x="30" y="246" width="790" height="640" fill="#FBFDFE"/>',
          f'<path d="{waterline(WL, 31, 819)} L819,886 L31,886 Z" fill="url(#water-cover)"/>', boat(),
          f'<path d="{waterline(WL, 31, 819)} L819,886 L31,886 Z" fill="#DDECF2" opacity=".55"/>',
          f'<path d="{waterline(WL, 31, 819)}" fill="none" stroke="{SEA}" stroke-width="1.6"/>']
    for r in (52, 70, 88):
        a0, a1 = math.radians(-22), math.radians(22)
        sc.append(f'<path d="M{32+r*math.cos(a0):.1f},{652+r*math.sin(a0):.1f} A{r},{r} 0 0 1 {32+r*math.cos(a1):.1f},{652+r*math.sin(a1):.1f}" fill="none" stroke="{WEED}" stroke-width="2" stroke-dasharray="5 5" stroke-linecap="round" opacity=".8"/>')
    for bx, by, br in ((560, 770, 4), (570, 752, 3), (556, 736, 2.5), (300, 770, 3), (310, 752, 2)):
        sc.append(f'<circle cx="{bx}" cy="{by}" r="{br}" fill="none" stroke="{SEA}" stroke-width="1.2" opacity=".6"/>')
    sc.append('<g transform="translate(5 106) scale(0.85)">' + fish('cover') + '</g>')
    s.append(f'<g clip-path="url(#scene-cover)">{"".join(sc)}</g>')
    s.append('<rect x="30" y="246" width="790" height="640" rx="14" fill="none" stroke="#DCE6EB"/>')
    s.append(f'<text x="50" y="282" font-size="10.5" font-weight="600" letter-spacing="1.5" fill="{MID}">ABOVE THE WATERLINE</text><text x="50" y="300" font-size="12.5" fill="{MID}">People and machines</text>')
    s.append(f'<text x="50" y="448" font-size="10.5" font-weight="600" letter-spacing="1.5" fill="{SEA}">BELOW THE WATERLINE</text><text x="50" y="466" font-size="12.5" fill="{SEA}">Biomimetic underwater robotics</text>')
    n = lambda part: nums[SCENE[part]['id']]
    sail = SCENE['sailor']
    s.append(label(616, 276, '', sail['kicker'], sail['desc'], None, (512, 350),
                   items=[(f'#{pid}', f'{nums[pid]}  {t}') for pid, t in sail['items']], w=30))
    for part, (x, y, tgt, kw) in {'tiller': (616, 384, (517, 381), {}), 'engine': (616, 448, (567, 400), {}),
                                  'lateral': (44, 512, T(330, 605), {'w': 34, 'start': (232, 582)}),
                                  'muscle': (616, 528, T(520, 640), {'w': 29}),
                                  'heart': (44, 790, T(268, 678), {'w': 34}),
                                  'fins': (616, 790, T(512, 712), {'w': 29})}.items():
        v = SCENE[part]
        is_now = v['id'] == NOW
        s.append(label(x, y, 'NOW' if is_now else n(part), v['kicker'], v.get('desc'), v['short'], tgt,
                       href=f'#{v["id"]}', **kw))
    s.append(f'<text x="804" y="876" font-size="9.5" letter-spacing="1" fill="#8FA3AE" text-anchor="end">FIG. 0 · SCHEMATIC · NOT TO SCALE</text>')
    return (f'<svg class="pfc-scene-art" viewBox="30 246 790 640" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="Table of contents drawn as a sailboat above the waterline and a fish below it, with each part labeled by its chapter">'
            + ''.join(s) + '</svg>')


def thumb(project_id):
    """Small scene drawing for a chapter header: (svg, kicker, text) or None."""
    part = part_of(project_id)
    if not part or 'thumb' not in SCENE[part]:
        return None
    kicker, text = SCENE[part]['thumb']
    uid = f't-{project_id}'
    if part in ('muscle', 'fins'):
        art = f'<svg class="pf-thumb-art" viewBox="160 500 560 250" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{fish(uid, hl=part)}</svg>'
    else:
        art = (f'<svg class="pf-thumb-art" viewBox="280 250 310 232" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
               f'<path d="{waterline(WL, 280, 590)} L590,482 L280,482 Z" fill="#E3F0F5"/>{boat(hl=part)}'
               f'<path d="{waterline(WL, 280, 590)} L590,482 L280,482 Z" fill="#DDECF2" opacity=".55"/>'
               f'<path d="{waterline(WL, 280, 590)}" fill="none" stroke="{SEA}" stroke-width="1.4"/></svg>')
    return art, kicker, text
