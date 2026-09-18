#!/usr/bin/env python3
"""Checks/규칙 준수.md 의 C1~C9 를 실행한다. 문제를 바꾸지 않는다."""
import os, re, sys, io, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", ".obsidian", ".trash", "Template", "Checks"}

# 사용자가 쓰는 곳. 규칙이 수정을 금지하므로 위반이 나와도 에이전트가 못 고친다.
# 검사 대상에서 빼지 않으면 "고칠 수 없는 FAIL"이 남는다.
USER_OWNED = ("Me/About Me", "Me/Braindump.md")

def md_files(*paths):
    out = []
    for base in paths:
        p = os.path.join(ROOT, base)
        if os.path.isfile(p):
            out.append(p); continue
        for d, subs, fs in os.walk(p):
            subs[:] = [x for x in subs if x not in SKIP_DIRS]
            out += [os.path.join(d, f) for f in fs if f.endswith(".md")]
    return sorted(out)

def rel(p): return os.path.relpath(p, ROOT)
def lines(p): return io.open(p, encoding="utf-8").read().splitlines()

def agent_files(*paths):
    """에이전트가 고칠 수 있는 산출물만 돌려준다."""
    out = []
    for p in md_files(*paths):
        r = rel(p)
        if any(r == u or r.startswith(u + os.sep) for u in USER_OWNED): continue
        out.append(p)
    return out

def diff_vs_head(relpath):
    """(이번에 늘어난 줄 번호, 이번에 사라진 줄 원문). git을 못 쓰면 None."""
    try:
        r = subprocess.run(["git", "diff", "-U0", "HEAD", "--", relpath],
                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    if r.returncode != 0: return None
    nums, gone = set(), []
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        m = re.match(r'^@@ -\S+ \+(\d+)(?:,(\d+))? @@', ln)
        if m:
            start = int(m.group(1))
            cnt = 1 if m.group(2) is None else int(m.group(2))
            nums.update(range(start, start + cnt)); continue
        if ln.startswith("-") and not ln.startswith("---"):
            gone.append(ln[1:])
    return nums, gone

results = []
def record(cid, title, hits, expect="0곳"):
    results.append((cid, title, hits, expect))

# C1 — 산출물에 규칙 번호 · 절 번호
RULE_NUM = re.compile(r'(?<![A-Za-z0-9])R(?:1[0-5]|[1-9])(?![0-9A-Za-z])')
SEC_NUM  = re.compile(r'§\s*\d')
hits = []
for p in agent_files("Me", "Daily", "Glossary", "Session", "Static", "Learning.md", "README.md"):
    for i, ln in enumerate(lines(p), 1):
        if RULE_NUM.search(ln) or SEC_NUM.search(ln):
            hits.append("%s:%d  %s" % (rel(p), i, ln.strip()[:80]))
record("C1", "산출물에 규칙 번호·절 번호", hits)

# C2 — 경고 표기
OK_WARN = ("⚠️ 완료", "⚠️ 추측:", "⚠️ 확신도:")
hits = []
for p in agent_files("Me", "Daily", "Glossary", "Session", "Static", "Learning.md", "README.md"):
    for i, ln in enumerate(lines(p), 1):
        for m in re.finditer("⚠️", ln):
            if not any(ln[m.start():].startswith(o) for o in OK_WARN):
                hits.append("%s:%d  %s" % (rel(p), i, ln.strip()[:80])); break
record("C2", "경고 표기가 정해진 곳 밖", hits)

# C3 — 해석 줄 확신도
# 사용자가 지운 표기는 "검증됨"이라는 신호다. 지난 줄까지 세면
# 시스템이 제대로 굴러갈수록 점수가 떨어진다. 이번에 추가한 줄만 본다.
hits = []
p = os.path.join(ROOT, "Me/Understanding.md")
d = diff_vs_head("Me/Understanding.md")
note = ""
if d is None:
    note = " · git을 못 써서 못 쟀다"
elif os.path.isfile(p):
    nums, gone = d
    for i, ln in enumerate(lines(p), 1):
        t = ln.strip()
        if i not in nums: continue
        if not t.startswith("- **해석**") or "⚠️ 확신도:" in t: continue
        # 같은 줄에서 확신도만 사라졌으면 사용자가 검증하고 지운 것이다
        if any(g.strip().startswith(t) and "⚠️ 확신도:" in g for g in gone): continue
        hits.append("Me/Understanding.md:%d  %s" % (i, t[:80]))
record("C3", "확신도 없는 해석 줄 (이번에 추가한 줄만%s)" % note, hits)

# C4 — 개념 백링크
hits = []
p = os.path.join(ROOT, "Glossary/_INDEX.md")
if os.path.isfile(p):
    for i, ln in enumerate(lines(p), 1):
        for name in re.findall(r'\[\[([^\]|#]+)', ln):
            name = name.strip()
            if not os.path.isfile(os.path.join(ROOT, "Glossary", name + ".md")):
                hits.append("Glossary/_INDEX.md:%d  [[%s]] → 파일 없음" % (i, name))
record("C4", "깨진 개념 백링크", hits)

# C5 — 데일리 빈 절
hits = []
for p in md_files("Daily"):
    ls = lines(p)
    for i, ln in enumerate(ls):
        if ln.strip() == "## 막힌 것":
            body = []
            for nxt in ls[i+1:]:
                if nxt.startswith("## ") or nxt.startswith("---"): break
                if nxt.strip() and not nxt.strip().startswith("<!--"): body.append(nxt)
            if not body: hits.append("%s:%d  %s 아래가 비었다" % (rel(p), i+1, ln.strip()))
record("C5", "데일리의 막힌 것이 비었나", hits)

# C6 — 인터뷰 질문 수
hits = []
p = os.path.join(ROOT, "Me/Interview.md")
n = 0
if os.path.isfile(p):
    n = sum(1 for ln in lines(p) if ln.strip().startswith("**Q"))
    if n > 5: hits.append("Me/Interview.md  질문 %d개 (5개 이하여야 함)" % n)
record("C6", "인터뷰 질문 수 (현재 %d개)" % n, hits, "5개 이하")

# ---- AGENTS.md 표 읽기 (C7·C8 공용) ----
AGENT = os.path.join(ROOT, "AGENTS.md")
BACKTICK = re.compile(r'`([^`]+)`')
PLACEHOLDER = re.compile(r'[<>]|YYYY')

def agent_table(heading):
    """AGENTS.md의 해당 제목 아래 첫 표의 행을 [셀 리스트]로 돌려준다."""
    if not os.path.isfile(AGENT): return []
    rows, inside, seen = [], False, False
    for ln in lines(AGENT):
        if ln.startswith("## "):
            if inside: break
            inside = heading in ln
            continue
        if not inside: continue
        s = ln.strip()
        if not s.startswith("|"):
            if seen and s.startswith("---"): break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells): continue
        if not seen:
            seen = True; continue
        rows.append(cells)
    return rows

# C7 — 규칙이 가리키는 템플릿이 실제로 있나
hits, n = [], 0
rows = agent_table("산출물 형식")
if not rows:
    hits.append("AGENTS.md  '산출물 형식' 표를 찾지 못했다")
for cells in rows:
    if len(cells) < 2: continue
    for m in BACKTICK.findall(cells[1]):
        if not m.startswith("Template/"): continue
        n += 1
        if not os.path.isfile(os.path.join(ROOT, m)):
            hits.append("AGENTS.md 산출물 형식 표  %s → 파일 없음" % m)
record("C7", "규칙이 가리키는 템플릿 (%d개 확인)" % n, hits)

# C8 — 규칙이 가리키는 파일·폴더가 실제로 있나
hits, n, base = [], 0, ""
rows = agent_table("파일 구조")
if not rows:
    hits.append("AGENTS.md  '파일 구조' 표를 찾지 못했다")
for cells in rows:
    if len(cells) < 2: continue
    cat = BACKTICK.sub("", cells[0]).replace("*", "").strip()
    if cat:
        base = "" if cat.startswith("Root") else cat.rstrip("/")
        if base:
            n += 1
            if not os.path.isdir(os.path.join(ROOT, base)):
                hits.append("AGENTS.md 파일 구조 표  %s/ → 폴더 없음" % base)
                base = ""; continue
    for m in BACKTICK.findall(cells[1]):
        if PLACEHOLDER.search(m): continue
        n += 1
        path = os.path.join(ROOT, base, m) if base else os.path.join(ROOT, m)
        ok = os.path.isdir(path) if m.endswith("/") else os.path.isfile(path)
        if not ok:
            hits.append("AGENTS.md 파일 구조 표  %s → 없음" % os.path.join(base, m))
record("C8", "규칙이 가리키는 파일·폴더 (%d개 확인)" % n, hits)

# C9 — 배운 것의 줄 형식
LEARN = re.compile(r'^- \d{4}-\d{2}-\d{2} · (함정|패턴|취향|도구) · 확신 (높음|중간|낮음) — \S')
hits, n = [], 0
p = os.path.join(ROOT, "Learning.md")
if os.path.isfile(p):
    ls = lines(p)
    start = next((i for i, ln in enumerate(ls) if ln.strip() == "## 기록"), None)
    if start is None:
        hits.append("Learning.md  '## 기록' 절이 없다")
    else:
        body = ls[start+1:]
        for i, ln in enumerate(body):
            if not ln.startswith("- "): continue
            n += 1
            ln_no = start + 2 + i
            if not LEARN.match(ln):
                hits.append("Learning.md:%d  줄 형식 어긋남  %s" % (ln_no, ln.strip()[:60]))
                continue
            tail = []
            for nxt in body[i+1:]:
                if nxt.startswith("- ") or nxt.startswith("#"): break
                tail.append(nxt.strip())
            for need in ("근거:", "버릴 때:"):
                if not any(t.startswith(need) for t in tail):
                    hits.append("Learning.md:%d  '%s' 줄 없음" % (ln_no, need))
record("C9", "배운 것의 줄 형식 (기록 %d줄)" % n, hits)

passed = sum(1 for _, _, h, _ in results if not h)
print("규칙 준수 — %d/%d 통과\n" % (passed, len(results)))
for cid, title, h, expect in results:
    print("%s  %s — %s" % ("PASS" if not h else "FAIL", cid, title))
    for x in h[:12]: print("       %s" % x)
    if len(h) > 12: print("       ... 외 %d곳" % (len(h) - 12))
print()
sys.exit(0 if passed == len(results) else 1)
