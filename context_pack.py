#!/usr/bin/env python3
"""Context packer — the retrieval habit, scripted.

Usage: python3 context_pack.py TICKER [--out pack.md] [--max-kb 40]

Given a ticker (or company-name fragment), assembles everything the next
research run should open FIRST, per the vault query recipe:
  1. Company note (full)
  2. Earnings previews + trade setups for the name (full)
  3. Latest dated research notes linking it (newest 3, full)
  4. Claims about it (full — small files)
  5. Calendar nodes mentioning it (full — small files)
  6. Its themes (thesis line each, not full notes)
  7. Macro regime snapshot (Rates / Risk appetite / Growth — frontmatter + regime line)
  8. Sector maps touching its themes (paths only)

Stdlib only. Read-only (never writes to the vault).
"""
import os
import re
import sys
import glob

def _default_vault():
    for cand in (os.environ.get('FINANCE_KG_ROOT'),
                 '/documents/Finance Knowledge Graph',
                 os.path.expanduser('~/Documents/Finance Knowledge Graph')):
        if cand and os.path.isdir(cand):
            return cand
    return '/documents/Finance Knowledge Graph'


VAULT = _default_vault()


def read(fp):
    with open(fp, errors='ignore') as f:
        return f.read()


def frontmatter(txt):
    m = re.match(r'---\n(.*?)\n---', txt, re.S)
    return m.group(1) if m else ''


def field_array(fm, key):
    """inline ["[[a]]", ...] values for key (flat only), plus bare "Theme"
    names (the older ';'-separated convention) verified against Themes/."""
    m = re.search(r'^' + key + r':\s*\[(.*)\]\s*$', fm, re.M)
    if not m:
        return []
    out = re.findall(r'\[\[([^\]]+)\]\]', m.group(1))
    for bare in re.findall(r'["\']([^"\']+)["\']', m.group(1)):
        if '[[' not in bare and os.path.exists(VAULT + '/Themes/' + bare + '.md') \
                and bare not in out:
            out.append(bare)
    return out


def resolve(query):
    """ticker (exact, case-insensitive) or name fragment -> (company file, ticker)."""
    q = query.strip()
    companies = glob.glob(VAULT + '/Companies/*.md')
    # 1. exact ticker match
    for fp in companies:
        fm = frontmatter(read(fp))
        m = re.search(r'^ticker:\s*"?([^"\n]+)"?', fm, re.M)
        tick = m.group(1).strip() if m else ''
        if tick.upper() == q.upper():
            return fp, tick
    # 2. alias match
    for fp in companies:
        fm = frontmatter(read(fp))
        for a in re.findall(r'"([^"]+)"', (re.search(r'^aliases:\s*\[(.*)\]', fm, re.M) or [None, ''])[1]):
            if a.upper() == q.upper():
                m = re.search(r'^ticker:\s*"?([^"\n]+)"?', fm, re.M)
                return fp, (m.group(1).strip() if m else q.upper())
    # 3. filename fragment
    frag = [fp for fp in companies if q.lower() in os.path.basename(fp)[:-3].lower()]
    if frag:
        fp = sorted(frag, key=lambda p: len(os.path.basename(p)))[0]
        fm = frontmatter(read(fp))
        m = re.search(r'^ticker:\s*"?([^"\n]+)"?', fm, re.M)
        return fp, (m.group(1).strip() if m else q.upper())
    return None, q.upper()


def notes_linking(link, folders=('Notes',)):
    hits = []
    for folder in folders:
        for fp in glob.glob(VAULT + '/' + folder + '/*.md'):
            if '[[' + link + ']]' in read(fp):
                hits.append(fp)
    return hits


def newest(paths, n):
    return sorted(paths, reverse=True)[:n]


def section(txt, heading, chars=1500):
    """first `chars` of a ## section, else ''."""
    m = re.search(r'^## ' + heading + r'\s*\n(.*?)(?=^## |\Z)', txt, re.M | re.S)
    return m.group(1).strip()[:chars] if m else ''


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    q = sys.argv[1]
    out = None
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    co_fp, tick = resolve(q)
    if not co_fp:
        print('no company resolves for: ' + q)
        return 1
    name = os.path.basename(co_fp)[:-3]
    co_txt = read(co_fp)
    co_fm = frontmatter(co_txt)
    themes = field_array(co_fm, 'themes') or field_array(co_fm, 'Themes')

    parts = []
    parts.append('# Context pack: %s (%s)' % (name, tick))
    parts.append('_Assembled from the Finance KG. Open edge: company -> research -> claims -> calendar. Read top-down._')
    parts.append('')
    parts.append('## 1. Company note: %s' % os.path.basename(co_fp))
    parts.append('```markdown')
    parts.append(co_txt[:12000])
    parts.append('```')

    # previews + setups
    specials = [fp for fp in glob.glob(VAULT + '/Notes/*.md')
                if os.path.basename(fp).startswith('2026-09-13')
                and ('preview' in fp or 'Trade setup' in fp)
                and ('[[' + name + ']]' in read(fp) or '[[' + tick + ']]' in read(fp))]
    parts.append('')
    parts.append('## 2. Previews + setups (%d)' % len(specials))
    for fp in sorted(specials):
        parts.append('### %s' % os.path.basename(fp))
        parts.append('```markdown')
        parts.append(read(fp)[:6000])
        parts.append('```')

    # latest research
    linked = [fp for fp in notes_linking(name) + notes_linking(tick)
              if 'preview' not in fp and 'Trade setup' not in fp]
    parts.append('')
    parts.append('## 3. Latest research notes (%d shown)' % min(3, len(linked)))
    for fp in newest(linked, 3):
        parts.append('### %s' % os.path.basename(fp))
        parts.append('```markdown')
        parts.append(read(fp)[:6000])
        parts.append('```')

    # claims
    claims = [fp for fp in glob.glob(VAULT + '/Claims/*.md')
              if '[[' + name + ']]' in read(fp)]
    parts.append('')
    parts.append('## 4. Claims about %s (%d)' % (name, len(claims)))
    for fp in sorted(claims):
        t = read(fp)
        m = re.search(r'^claim:\s*"(.*)"\s*$', frontmatter(t), re.M)
        st = re.search(r'^status:\s*"?(\w+)"?', frontmatter(t), re.M)
        parts.append('- [%s] %s — %s' % (
            st.group(1) if st else '?', os.path.basename(fp),
            (m.group(1)[:220] if m else '')))

    # calendar
    cal = [fp for fp in glob.glob(VAULT + '/Important Dates/*.md')
           if '[[' + name + ']]' in read(fp) or '[[' + tick + ']]' in read(fp)]
    parts.append('')
    parts.append('## 5. Calendar nodes (%d)' % len(cal))
    for fp in sorted(cal)[:10]:
        t = read(fp)
        fm = frontmatter(t)
        ds = re.search(r'^date_status:\s*"?(\w+)"?', fm, re.M)
        parts.append('- %s (%s)' % (os.path.basename(fp),
                                    ds.group(1) if ds else 'filed'))

    # themes (thesis lines)
    parts.append('')
    parts.append('## 6. Themes (%d)' % len(themes))
    for th in themes:
        tfp = VAULT + '/Themes/' + th + '.md'
        if os.path.exists(tfp):
            ttxt = read(tfp)
            tfm = frontmatter(ttxt)
            nm = re.search(r'^notes:\s*"(.*)"\s*$', tfm, re.M)
            if nm:
                line = nm.group(1)[:200]
            else:
                dm = re.search(r'^description:\s*"(.*)"\s*$', tfm, re.M)
                if dm:
                    line = dm.group(1)[:200]
                else:
                    body = ttxt.split('---', 2)[-1].strip().split('\n')
                    line = next((b.strip('# ').strip()[:200] for b in body if b.strip() and not b.startswith('[[')), '')
            parts.append('- [[%s]] — %s' % (th, line if line else ''))
        else:
            parts.append('- [[%s]] — (no theme file)' % th)

    # macro snapshot
    parts.append('')
    parts.append('## 7. Macro snapshot (Sep-2026 vintage — re-check before trading)')
    for mc in ('Rates', 'Risk appetite', 'Growth recession risk'):
        mfp = VAULT + '/Market Context/' + mc + '.md'
        if os.path.exists(mcfp := mfp):
            mt = read(mcfp)
            mfm = frontmatter(mt)
            rg = re.search(r'^regime:\s*"(.*)"\s*$', mfm, re.M)
            lu = re.search(r'^last_updated:\s*"(.*)"\s*$', mfm, re.M)
            parts.append('- %s: %s (updated %s)' % (
                mc, rg.group(1) if rg else '?', lu.group(1) if lu else '?'))

    # maps touching its themes
    parts.append('')
    parts.append('## 8. Sector maps touching its themes (paths — open the relevant one)')
    for fp in sorted(glob.glob(VAULT + '/Notes/*map research.md')):
        t = read(fp)
        shared = [th for th in themes if '[[' + th + ']]' in t]
        if shared:
            parts.append('- %s (shares: %s)' % (
                os.path.basename(fp), ', '.join(shared[:4])))

    doc = '\n'.join(parts)
    if out:
        with open(out, 'w') as f:
            f.write(doc)
        print('wrote %s (%d KB)' % (out, len(doc) // 1024))
    else:
        print(doc)
    return 0


if __name__ == '__main__':
    sys.exit(main())
