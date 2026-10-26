#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Kokonoha
# english-paper-skim — 論文の骨読み。GNU Affero General Public License v3.0 以降の条件で使える（同梱の LICENSE を見ること）。
"""英語論文の骨を取り出す（標準ライブラリだけ。PDF は pdftotext があれば使う）。
使い方:
  骨を取り出す:   python3 skeleton.py <arXiv ID | URL | file.html | file.txt | file.pdf>
  段落だけ読む:   python3 skeleton.py <同上> --paragraph "<骨に出た文の一部や語>"
  節ごと読む:     python3 skeleton.py <同上> --section "<骨に出た文の一部や語>"
  章ごと読む:     python3 skeleton.py <同上> --chapter "<骨に出た文の一部や語>"
  結論の章を読む: python3 skeleton.py <同上> --conclusion
  要旨を丸ごと読む: python3 skeleton.py <同上> --abstract
  語の出てくる文:   python3 skeleton.py <同上> --word "<語>"
  見出しの無い利益相反の候補も見る: python3 skeleton.py <同上> --coi-scan
  断章の本の骨:     python3 skeleton.py <同上> --fragments
  断章を一つ読む:   python3 skeleton.py <同上> --fragment <番号>
読む順番は、語 → 段落 → 節 → 章 → 結論の章 → 要旨 → 全文。矢印は「理解できなかったら、次へ」の意味。全文は最後の手段。
"""
import sys, re, html, os, subprocess, urllib.request, urllib.error

MARKERS = {
    "新しさ・対比": [r"\bHowever\b", r"\bIn contrast\b", r"\bUnlike\b", r"\bAlthough\b", r"\bwhereas\b",
                  r"\bfor the first time\b", r"\bpreviously\b", r"\bfalsif", r"\bcounterexample"],
    "主張": [r"\bWe (show|prove|present|demonstrate|find|establish|introduce|propose)\b", r"\bHere,? we\b",
           r"\bOur (main )?(result|contribution|finding)s?\b", r"\bIn this (paper|work|(systematic )?review|meta-analysis|study|analysis|trial)\b",
           r"\b(We|I) (find|document|estimate|exploit|quantify|provide|report|identify|develop|derive)\b", r"\bI (show|prove|present|demonstrate|establish|introduce|propose)\b",
           r"(?i)\bthis (systematic review|review|meta-analysis|analysis|trial|investigation) (aims|shows|showed|found|finds|provides|reports|indicates|suggests|demonstrates|confirms|examines|evaluates|investigates|is the first)\b",
           r"(?i)\bthis (paper|article|study) (studies|documents|estimates|quantifies|exploits|provides|reports|finds|found)\b",
           r"^(Main )?Theorem( [\dA-Z][\d.]*)?( \([^)]{0,80}\))?:",
           r"\bThis (paper|work|article|report) (presents|proposes|introduces|shows|argues|develops)\b",
           r"(?i)\bthis (article|essay|note|comment|chapter|paper|study|research) (aims|argues|proposes|contends|suggests|examines|explores|shows|demonstrates|offers|develops|analy[sz]es|analy[sz]ed|challenges|investigates|addresses|seeks)\b",
           r"\b(is|are) (presented|proposed|introduced|formalized|formalised|demonstrated|shown|derived|developed)\b",
           r"\bThis (Article|Note|Essay|Comment|chapter) (argues|proposes|contends|examines|shows|claims|suggests|explores|offers)\b"],
    "残っていること": [r"\bremains? (unknown|open|unclear)\b", r"\bopen (question|problem)s?\b", r"\bfuture (work|research)\b",
                  r"\blimitation", r"\bwe do not\b", r"\bnot (yet )?(known|clear|addressed)\b", r"\bleave[s]? .* to future"],
    "論証（反論と応答）": [r"\b(I|We) (will |shall )?(argue|defend|claim|contend|maintain)\b", r"\bMy (main )?(thesis|claim|argument|view|conclusion)\b", r"\bIn my view\b", r"\bI think that\b",
               r"\b(One|Someone|A critic) (might|could|may) (object|reply|respond|worry)\b", r"\bIt (might|could|may) be objected\b",
               r"\b(In|By way of) (reply|response)\b", r"\bobjections?\b", r"\bpremises?\b"],
    "構成（ロードマップ）": [r"\bPart (I|II|III|IV|V|VI|One|Two|Three|Four|Five)\b.{0,100}\b(describes|discusses|argues|examines|explains|turns|considers|addresses|concludes|sets out|analy[sz]es|explores|proposes|outlines)\b",
               r"(?i)\bsection (one|two|three|four|five|six) (develops|describes|discusses|argues|examines|explains|turns|considers|addresses|concludes|analy[sz]es|explores|outlines|presents)\b",
               r"\b(Section|Sections) (2|3|4|5|II|III|IV)\b.{0,100}\b(describes|discusses|argues|examines|explains|turns|considers|addresses|concludes|analy[sz]es|explores|outlines)\b",
               r"(?i)\b(the )?(first|second|third|fourth|final|last) (part|section) of (the|this) (paper|article|study)\b",
               r"(?i)\b(is (divided|organi[sz]ed|structured) (into|as follows))\b"],
    "定義": [r"\b(We|we) (define|call|denote|refer to|term)\b", r"\b(is|are) defined (as|by)\b", r"\brefers? to\b", r"\bDefinition\s*\d*[.:]", r"\bby (definition|which we mean)\b", r"\bhereafter\b", r"\bwe use the term\b"],
    "資料（データ・コード・出典）": [r"\b(data|dataset|datasets|code|software|materials?) (are|is) (publicly |freely |openly )?available\b", r"\bavailable (at|from|on|upon) (https?://|github|zenodo|figshare|osf|the (corresponding )?authors?|request|reasonable request)", r"\bgithub\.com\b", r"\bzenodo\b", r"\bdoi\.org\b", r"\bwe (use|used|collected|analy[sz]ed) (the |a |an )?[\w\- ]{0,40}(dataset|data|corpus|cohort|sample|archive|records)\b", r"\bData (and code )?availability\b", r"\bSupplementary (Information|Data|Materials?)\b"],
    "帰結": [r"\bThus\b", r"\bTherefore\b", r"\bThis (implies|means|suggests)\b", r"\bthus advance"],
}
SPECIAL = {
    "AIの使用": [r"\b(used|using|with the (help|assistance) of|assisted|drafted|generated|discovered|written)\b.{0,80}\b(GPT|Claude|Gemini|ChatGPT|LLM|language model|artificial intelligence|AI (model|tool|assistant))",
               r"\b(GPT|Claude|Gemini|ChatGPT)[\w\s\-\.]{0,30}\b(was|were) used\b"],
    "利益相反": [r"\b(consultan(t|cy)|honorari(a|um)|conflicts? of interests?|competing (financial )?interests?|declarations? of (competing )?interests?|duality of interests?)\b", r"\bThe authors? (declares?|reports?|ha(s|ve)) (that (they|he|she) (have|has) )?no\b", r"\bdisclosures? to (declare|report)\b", r"\b(financial|non-financial) disclosure:"],
}

ARXIV_ID = r"(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?)"

def arxiv_id(arg):
    m = re.search(ARXIV_ID, arg)
    return m.group(1) if m else None

MAX_BYTES = 60 * 1024 * 1024   # 取得量の上限（60MB）

def fail(msg, code=2):
    print("（失敗）" + msg, file=sys.stderr); sys.exit(code)

def pdf_to_text(path):
    """PDF を文字にする。変換の失敗と、文字が空のときを分けて止める（F3）"""
    try:
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        fail("pdftotext が入っていないので、PDF を読めない")
    except subprocess.TimeoutExpired:
        fail("PDF の変換が 180 秒で終わらなかった")
    if out.returncode != 0:
        fail("PDF の変換に失敗した（pdftotext の終了コード %d）：%s" % (out.returncode, out.stderr.strip()[:300]))
    if not out.stdout.strip():
        fail("PDF から文字が取れなかった（画像だけの PDF の可能性）")
    return out.stdout

def fetch(arg):
    if re.fullmatch(ARXIV_ID, arg):
        arg = "https://arxiv.org/html/" + arg
    if re.match(r"^[a-z]+://", arg) and not arg.startswith(("http://", "https://")):
        fail("http と https 以外の URL は読まない：" + arg)
    if arg.startswith("http"):
        if "arxiv.org/abs/" in arg or "arxiv.org/pdf/" in arg:
            aid = arxiv_id(arg)
            if not aid: fail("arXiv の番号の形が分からない：" + arg)
            arg = "https://arxiv.org/html/" + aid
        req = urllib.request.Request(arg, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as e:
            if e.code == 404 and "arxiv.org/html/" in arg:   # HTML 版の無い arXiv の論文は PDF で読む
                req = urllib.request.Request(arg.replace("/html/", "/pdf/"), headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=90)
            else:
                raise
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: fail("取得した大きさが上限（60MB）を超えた")
        ctype = resp.headers.get("Content-Type", "")
        if data[:5] == b"%PDF-" or "pdf" in ctype.lower():   # arXiv 以外の PDF の URL
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f: f.write(data); tmp = f.name
            try:
                return pdf_to_text(tmp), "txt"
            finally:
                if os.path.exists(tmp): os.remove(tmp)
        return data.decode("utf-8", "ignore"), "html"
    if arg.lower().endswith(".pdf"):
        return pdf_to_text(arg), "txt"
    if os.path.exists(arg) and os.path.getsize(arg) > MAX_BYTES: fail("ファイルの大きさが上限（60MB）を超えた")
    t = open(arg, encoding="utf-8-sig", errors="ignore").read()
    return t, ("html" if arg.lower().endswith((".html", ".htm", ".xml")) else "txt")

def struct_abstract(raw):
    """JATS の <abstract> や、HTML の要旨の枠を、要素の境界で取る（I2）。取れなければ空"""
    m = re.search(r"<abstract(?![^>]*abstract-type=\"(graphical|teaser)\")[^>]*>(.*?)</abstract>", raw, re.S | re.I)
    if not m:
        m = re.search(r"<div[^>]*class=\"[^\"]*ltx_abstract[^\"]*\"[^>]*>(.*?)</div>", raw, re.S | re.I)
        if not m: return ""
        body = m.group(1)
    else:
        body = m.group(2)
    body = re.sub(r"<(title|h\d)[^>]*>\s*Abstract\s*</\1>", " ", body, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", t).strip()

def html_to_text(s):
    m = re.search(r"<article\b[^>]*ltx_document[^>]*>.*?</article>", s, re.S)   # arXiv の HTML 版は、本文の外の案内（Report Issue、Back to Abstract など）を落とす
    if m: s = m.group(0)
    s = re.sub(r"<(nav|header|footer)\b.*?</\1>", " ", s, flags=re.S)   # 出版社の HTML の案内の帯も落とす
    s = re.sub(r'<div class="ltx_authors">.*?(?=<div[^>]*class="ltx_abstract")', " ", s, flags=re.S)   # 著者と所属の塊は、目印の文に混ざるので落とす（題は別に取る）
    s = re.sub(r'<math.*?alttext="(.*?)".*?</math>', lambda m: " " + html.unescape(m.group(1))[:40] + " ", s, flags=re.S)
    s = re.sub(r"<(script|style).*?</\1>", "", s, flags=re.S)
    s = re.sub(r"</(p|div|h[1-6]|li|figcaption|section|title|sec|abstract)>", "\n\n", s)   # JATS（PMC の全文 XML）の見出しも段落として切る
    s = re.sub(r"<abstract[^>]*>", "\n\nAbstract\n\n", s)   # F4：要旨の枠を見出しとして残す
    s = re.sub(r"<(title|sec)[^>]*>", "\n\n", s)
    t = re.sub(r"<[^>]+>", " ", s)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t)


MATH_PARA = re.compile(r"\\(frac|sum|int|prod|mathrm|mathcal|mathbb|left|right|hat|tilde|bar|operatorname|langle|rangle|otimes|rho|psi|phi|alpha|beta|gamma|sigma|omega|lambda|mu|nu|partial|nabla|infty|cdot|times|leq|geq|neq|equiv|propto|begin\{|displaystyle)|^\s*[\\(\[=]|[=≤≥≠∈∑∫∏⊗√∂∞]")

def is_math_paragraph(p):
    """数式の段落か（LaTeX の命令か数学記号を含み、英字の比率が低い）"""
    q = p.strip()
    if not q: return False
    letters = len(re.findall(r"[A-Za-z]", q))
    words = len(re.findall(r"\b[A-Za-z]{3,}\b", q))
    if MATH_PARA.search(q) and (letters / max(1, len(q)) < 0.55 or words < 6): return True
    return letters / max(1, len(q)) < 0.4 and len(q) < 400

def join_math_paragraphs(text):
    """空行で切った段落のうち、数式の段落と、その前後（文の途中で式が挟まる形）を一つに繋ぐ。
    前の段落が句点で終わらず次が小文字で始まるときも続きとして繋ぐ。戻り値は段落の列"""
    paras = [p for p in re.split(r"\n\s*\n+", text) if p.strip() and re.search(r"[A-Za-z0-9\\]", p)]   # 箇条書きの印だけの段落（•）は落とす
    out = []
    for p in paras:
        q = p.strip()
        if out:
            prev = out[-1].rstrip()
            glue = is_math_paragraph(q) or is_math_paragraph(prev.split("\n")[-1] if "\n" in prev else prev) and not re.search(r"[.!?:]\s*$", prev) \
                   or (not re.search(r"[.!?:]\s*$", prev) and re.match(r"[a-z]", q)) \
                   or (not re.search(r"[.!?:]\s*$", prev) and is_math_paragraph(prev[-200:]))
            if glue:
                out[-1] = out[-1] + " " + q; continue
        out.append(q)
    return out

def sentences(text):
    text = re.sub(r"\$?[*†‡§]\$?\s*\$?[*†‡§]?\$?\s*footnotetext:.*?(?=(?:\$?[*†‡§]|$))", " ", text)
    text = re.sub(r"footnotetext:[^.]*\.", " ", text)
    text = re.sub(r"\$[^$]{0,25}\$", " ", text)            # 脚注の印などの短い式
    text = re.sub(r"\\bullet\b", " ", text)                 # 箇条書きの印の式
    text = re.sub(r"\{?\s*[\w.\-]+@[\w.\-]+(\s*,\s*[\w.\-]+@[\w.\-]+)*\s*\}?", " ", text)  # メールアドレス
    text = "\ue000".join(join_math_paragraphs(text))   # 段落（空行）の境は文の境にもする（題や見出しが次の文にくっつかない）。数式の段落の前後は境にしない
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b((?:Main )?Theorem)\s+([\dA-Z][\d.]*?)\.?\s*(\([^)]{0,80}\))?\.\s+", lambda m: m.group(1) + " " + m.group(2) + (" " + m.group(3) if m.group(3) else "") + ": ", text)   # 定理の番号で文を切らない
    text = re.sub(r"\b(et al|Fig|Figs|Eq|Eqs|Sec|Secs|Ref|Refs|Tab|Thm|Prop|Lem|Cor|Def|cf|e\.g|i\.e|vs|Vol|pp|Dr|Mr|Ms|Prof|Univ|Dept|Inc|Ltd|Co)\.(?=\s+[A-Z(])", lambda m: m.group(0).replace(".", "\ue001"), text)   # 略語のピリオドで文を切らない（et al. / Fig. / Eq. / Sec. など）
    text = re.sub(r"\bNo\.(?=\s*\d)", "No\ue001", text)   # 「No. 5」の番号の前だけ保護し、否定の「No.」では切る
    out = [x.strip().replace("\ue001", ".") for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(])|\s*\ue000\s*", text)]
    return [x for x in out if re.search(r"[A-Za-z]", x) and len(x) >= 2]   # I4：長さでは捨てない

def section(text, start_pats, end_pats):
    lines = text.split("\n")
    idx = [i for i, l in enumerate(lines) if len(l.strip()) <= 160 and any(re.match(p, l.strip(), re.I) for p in start_pats)]   # 見出しは短い。折り返された本文の行は候補にしない
    if not idx: return ""
    best, best_closed = "", ""
    for i in idx:  # 目次や末尾の案内ではなく本文の節を取るため、終わりの見出しまで閉じた中でいちばん長いものを使う
        out, closed = [], False
        first = lines[i].strip()   # F5：見出しと同じ行に本文が続いていれば、それも残す（例「Abstract. We show ...」）
        for sp in start_pats:
            mm = re.match(sp, first, re.I)
            if mm:
                rest = first[mm.end():].lstrip(" .:—-")
                if re.search(r"[A-Za-z\u3040-\u30ff\u4e00-\u9fff]", rest): out.append(rest)   # I4：同じ行の短い本文も残す
                break
        for l in lines[i + 1:]:
            if any(re.match(p, l.strip(), re.I) for p in end_pats) and out:
                closed = True; break
            out.append(l)
        cand = "\n".join(out).strip()
        if closed and len(cand) > len(best_closed): best_closed = cand
        if len(cand) > len(best): best = cand
    return best_closed or best

def paragraphs(t):
    return [p.strip() for p in re.split(r"\n\s*\n", t) if len(p.strip()) > 80 and "·" not in p]

HEAD = re.compile(r"^((\d+(\.\d+)*)|[IVX]+|[A-Z])\.?\s+[‘'“\"(]?[A-Z][^\n]{1,80}$")
HEAD_UNNUM = re.compile(r"^(Abstract|Introduction|Background|Related [Ww]ork|Materials and [Mm]ethods|Methods?|Methodology|Results?|Results and [Dd]iscussion|Discussion|Conclusions?|Concluding [Rr]emarks|Limitations|Summary|Outlook|Acknowledg\w*|References|Bibliography|Appendix\w*)\s*$")

def is_head(h):
    return bool(HEAD.match(h) or HEAD_UNNUM.match(h))

def head_level(h):
    m = re.match(r"^(\d+(\.\d+)*)", h)
    return m.group(1).count(".") if m else 0

def norm(x):
    return re.sub(r"\s+", " ", x).strip()

BACK_HEADS = r"^(References|Bibliography|Acknowledg\w*|Funding( information)?|Author contributions?|Data (and code )?availability|Code availability|Appendix\w*|Supplementary\w*|Ethics\w*|Abbreviations|Additional information|Footnotes|Notes|Declarations?|Competing interests?|Conflicts? of interests?|Disclosures?|Duality of interests?)\b"

def block_after_heading(text, head_pats, limit=3000):
    """見出しのあとの本文を、次の見出し（決まった見出しの語、または番号付きの見出し）まで取る。
    戻り値は (見出しがあったか, 本文)。本文が空でも、見出しがあったことは失わない（I3）"""
    lines = text.split("\n")
    for i, l in enumerate(lines):
        h = l.strip()
        m = next((re.match(p, h, re.I) for p in head_pats if re.match(p, h, re.I)), None)
        if not m: continue
        out = []
        rest = h[m.end():].lstrip(" .:—-")
        if re.search(r"[A-Za-z]", rest): out.append(rest)
        for l2 in lines[i + 1:]:
            h2 = l2.strip()
            if h2 and (re.match(BACK_HEADS, h2, re.I) or HEAD.match(h2) or HEAD_UNNUM.match(h2)) and not any(re.match(p, h2, re.I) for p in head_pats):
                break
            out.append(l2)
        return True, re.sub(r"\s+", " ", " ".join(out)).strip()[:limit]
    return False, ""

def find_paragraph(text, query):
    q = norm(query).lower()
    paras = [p for p in re.split(r"\n\s*\n", text) if norm(p)]
    hits = [norm(p) for p in paras if q in norm(p).lower()]   # I5：長さで除かない（長いものを優先）
    return max(hits, key=len) if hits else ""

def find_section(text, query, top=False):
    lines = text.split("\n")
    q = norm(query).lower()
    # 問いの語を含む行のうち、本文の中にあるもの（いちばん長い段落の中）を探す
    target = None
    for i, l in enumerate(lines):
        if q in norm(l).lower() and not is_head(l.strip()): target = i if target is None or len(norm(l)) > len(norm(lines[target])) else target   # I5：長さで除かない
    if target is None: return "", ""
    start = None
    for i in range(target, -1, -1):
        h = lines[i].strip()
        if is_head(h) and (not top or not re.match(r"^\d+\.\d", h)): start = i; break
    if start is None:
        return "（見出しが見つからず、節の境目が分からない。語を含む段落だけを返す）", find_paragraph(text, query)
    head = lines[start].strip()
    level = head_level(head)
    out = []
    for l in lines[start + 1:]:
        h = l.strip()
        if is_head(h) and head_level(h) <= level: break
        out.append(l)
    return head, re.sub(r"\n\s*\n+", "\n\n", "\n".join(out)).strip()

CONC_START = [r"^(\d+|[IVX]+)\.?\s+(Discussion|Conclusions?|Summary|Concluding|Outlook)", r"(?-i:^(Discussion|Conclusions?|Summary|Concluding remarks))\b"]   # 番号の無い見出しは大文字始まりだけ（本文の行頭の discussion を見出しと取り違えない）
CONC_END = [r"^Acknowledg", r"^References\b", r"^Appendix", r"^Bibliography", r"(?-i:^[A-Z]\s+[A-Z][a-z]+)", r"(?-i:^(\d+|[IVX]+)\.?\s+[‘'“\"(]?[A-Z][a-z])", r"^(Research|Study) (design|methods?)\b", r"^(Patients|Subjects|Participants|Data|Materials?) and methods?\b", r"^(Introduction|Background|Related [Ww]ork|Materials and [Mm]ethods|Methods?|Methodology|Results?|Limitations)\s*$"]

INTRO_END = [r"^(Research|Study) (design|methods?)\b", r"^(Patients|Subjects|Participants|Data|Materials?) and methods?\b",
             r"^(Design|Methods?) and \w+\s*$", r"^Experimental (procedures|section)\b", r"^(Discussion|Conclusions?)\s*:"]   # 方法の見出しの言い換え（雑誌ごとの形）

def last_chapter(text):
    """結論の見出しが無い論文では、本文の最後の章（参考文献や謝辞の前）を結論の章とみなす"""
    lines = text.split("\n")
    stop = len(lines)
    for i, l in enumerate(lines):
        if re.match(r"^(References|Bibliography|Acknowledg)", l.strip()) and i > len(lines) * 0.3: stop = i; break
    tops = [i for i in range(stop) if re.match(r"^(\d+|[IVX]+)\.?\s+[‘'“\"(]?[A-Z][^\n]{1,80}$", lines[i].strip())]
    if not tops: return "", ""
    i = tops[-1]
    return lines[i].strip(), "\n".join(lines[i + 1:stop]).strip()

def conclusion(text):
    c = section(text, CONC_START, CONC_END)
    if c: return "", c
    return last_chapter(text)

def arxiv_title(arg):
    """arXiv の番号や URL なら、要旨のページの citation_title から題を取る（HTML 版に題の見出しが無い論文のため）"""
    aid = arxiv_id(arg) if ("arxiv.org" in arg or re.fullmatch(ARXIV_ID, arg)) else None
    if not aid: return ""
    m = re.match(r"(.+?)(v\d+)?$", aid)
    try:
        req = urllib.request.Request("https://arxiv.org/abs/" + m.group(1), headers={"User-Agent": "Mozilla/5.0"})
        page = urllib.request.urlopen(req, timeout=30).read(MAX_BYTES).decode("utf-8", "ignore")
        t = re.search(r'<meta name="citation_title" content="([^"]+)"', page)
        return html.unescape(t.group(1)).strip() if t else ""
    except Exception:
        return ""


# ---------------- 日本語の論文（Markdown の見出しで章立てしたもの）----------------
JA_MARKERS = {
    "主張": [r"本稿(は|では)", r"本論(は|では)", r"と定義する", r"と呼ぶ", r"を提案する", r"を示す", r"とする。", r"を論ずる", r"を問う"],
    "新しさ・対比": [r"^しかし", r"一方", r"ではなく", r"これに対し", r"従来", r"とは異なり"],
    "残っていること": [r"未検証", r"未確定", r"今後の課題", r"今後", r"確定しない", r"決まらない", r"限界", r"保留", r"未実施", r"課題として"],
    "論証（反論と応答）": [r"反論", r"なぜなら", r"であるならば", r"のであれば", r"と考えられる"],
    "定義": [r"と定義する", r"と呼ぶ", r"(?<!こ)とは[、，]", r"を指す", r"の意味で用いる", r"と置く"],
    "資料（データ・出典）": [r"資料", r"データ", r"出典", r"記録", r"コーパス", r"https?://", r"doi\.org", r"［\d+］", r"\[\d+\]"],
    "帰結": [r"^ゆえに", r"^したがって", r"^よって", r"^つまり", r"結論として"],
}
JA_SKIP = r"(改訂履歴|変更履歴|参考文献|目次|独立検証で必要となる資料)"

def is_japanese(t):
    ja = len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", t))
    return ja > len(t) * 0.15

def ja_sections(t, skip=None):
    """Markdown の見出し（#）で、日本語の論文を節に分ける。戻り値は [(見出し, 本文)]。
    skip に当たる見出しの章は、その子の見出しの節も丸ごと除く（F6）"""
    out, head, buf, depth = [], "（冒頭）", [], 0
    skipping_at = None
    cur_skipped = False
    for l in t.split("\n"):
        m = re.match(r"^(#{1,6})\s*(.+?)\s*$", l)
        if m:
            if not cur_skipped: out.append((head, "\n".join(buf).strip()))
            depth, head, buf = len(m.group(1)), m.group(2), []
            if skipping_at is not None and depth <= skipping_at: skipping_at = None
            if skip and skipping_at is None and re.search(skip, head): skipping_at = depth
            cur_skipped = skipping_at is not None
        else:
            buf.append(l)
    if not cur_skipped: out.append((head, "\n".join(buf).strip()))
    return [(h, b) for h, b in out if b or h]

def ja_sentences(t):
    t = re.sub(r"^\s*[-*>|]+\s*", "", t, flags=re.M)
    return [x.strip() for x in re.split(r"(?<=[。！？])\s*|\n+", t) if re.search(r"[\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9]", x)]   # I4：長さでは捨てない

def ja_paragraphs(t):
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", t) if len(p.strip()) > 40 and not p.strip().startswith("|")]

def main_ja(text, arg):
    secs = ja_sections(text)
    title = next((h for h, b in secs if h != "（冒頭）"), "")
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m: title = m.group(1).strip()
    body_secs = ja_sections(text, skip=JA_SKIP)
    abstract = next((b for h, b in body_secs if re.search(r"要旨|要約|概要|アブストラクト", h)), "")
    numbered = [(h, b) for h, b in body_secs if re.match(r"^\d", h)]
    intro = next((b for h, b in body_secs if re.search(r"はじめに|序論|序章|導入", h)), numbered[0][1] if numbered else "")
    concl_cands = [(h, b) for h, b in body_secs if re.search(r"結論|おわりに|まとめ|結び", h)] or [(h, b) for h, b in body_secs if re.search(r"考察", h)]
    concl_head, concl = (concl_cands[-1] if concl_cands else ((numbered[-1][0], numbered[-1][1]) if numbered else ("", "")))
    print(f"# 骨読み — {title}\n")
    a = ja_sentences(abstract)
    if a: print("## 要旨の最後の二文\n"); [print("- " + x) for x in a[-2:]]; print()
    ip = ja_paragraphs(intro)
    if ip: print("## 導入の最初と最後の段落\n\n" + ip[0][:400] + ("\n\n" + ip[-1][:400] if len(ip) > 1 else "") + "\n")
    cp = ja_paragraphs(concl)
    if cp:
        print(f"## 結論の段落（「{concl_head}」）\n\n" + cp[0][:500] + ("\n\n" + cp[-1][:500] if len(cp) > 1 else "") + "\n")
    print("## 章立て\n"); [print("- " + h) for h, b in body_secs if re.match(r"^(\d|要旨|結論|はじめに|考察)", h)]; print()
    core = [x for h, b in body_secs for x in ja_sentences(b)]
    for name, pats in JA_MARKERS.items():
        seen = set()   # F8：分類ごとに数える
        hits = []
        for x in core:
            k = x[:80]
            if any(re.search(pp, x) for pp in pats) and k not in seen:
                hits.append(x); seen.add(k)
            if len(hits) >= 4: break
        if hits: print(f"## 目印：{name}\n"); [print("- " + h[:220]) for h in hits]; print()


# ---------------- 断章の本（番号付きの断章や箴言でできた本）----------------
FRAG_LINE = re.compile(r"^\s*(§\s*)?(\d{1,4}(?:\.\d{1,4})*)\.?\s+(?=[A-Z\"“'(\[—])")   # I6：「43.」も「1.11」も

def fragments(text):
    """番号付きの断章に切る。ページ番号などの雑音を避けるため、番号がほぼ順に進むものだけを採る"""
    lines = text.split("\n")
    cuts, last = [], 0
    for i, l in enumerate(lines):
        m = FRAG_LINE.match(l)
        if not m: continue
        label = m.group(2)
        if "." not in label and not re.match(r"^\s*(§\s*)?\d{1,4}\.\s", l): continue   # 整数の番号は「43.」の形だけ（本文中の数字を拾わない）
        top = int(label.split(".")[0])
        if (last < top <= last + 3) or ("." in label and top == last):   # 順に進む番号、または今の番号の下の小数の番号
            cuts.append((label, i)); last = top
    out = []
    for k, (n, i) in enumerate(cuts):
        j = cuts[k + 1][1] if k + 1 < len(cuts) else len(lines)
        body = re.sub(r"\s+", " ", " ".join(lines[i:j])).strip()
        body = re.sub(r"^(§\s*)?\d{1,4}(\.\d{1,4})*\.?\s+", "", body)
        out.append((n, body))
    return out

FRAG_MARKERS = {
    "主張・定義": [r"\bis (its|the|a|an) ", r"\bmeans\b", r"\bcan be defined\b", r"\bI (say|claim|mean)\b", r"\bmust\b"],
    "反論と応答（対話）": [r"—\s*But\b", r"\bBut (isn't|is not|surely|then)\b", r"\bOne (might|may|could|would) (say|object|think)\b", r"\bobjection\b", r"\bI want to say\b"],
    "問い": [r"\?\s*$", r"^(But |And )?(What|How|Why|Is|Does|Can|Could)\b[^.]*\?"],
    "想像の例（思考実験）": [r"\bImagine\b", r"\bSuppose\b", r"\bThink of\b", r"\bLet us imagine\b"],
    "方法についての言葉": [r"\bphilosoph", r"\bgrammar\b", r"\blanguage-game", r"\bmisunderstand"],
}

def first_sentence(b, limit=180):
    m = re.match(r"(.+?[.!?])(\s|$)", b)
    return (m.group(1) if m else b)[:limit]

def main_fragments(frs, title):
    print(f"# 骨読み（断章の本） — {title}\n")
    print(f"## 断章の数\n\n{len(frs)} 個（番号 {frs[0][0]}〜{frs[-1][0]}）\n")
    print("## 最初の三つの断章の最初の文\n"); [print(f"- §{n}: " + first_sentence(b)) for n, b in frs[:3]]; print()
    print("## 最後の断章の最初の文\n"); print(f"- §{frs[-1][0]}: " + first_sentence(frs[-1][1])); print()
    for name, pats in FRAG_MARKERS.items():
        hits = []
        for n, b in frs:
            fs = first_sentence(b, 400)
            if any(re.search(pp, fs) for pp in pats): hits.append((n, fs))
        if hits:
            step = max(1, len(hits) // 6)   # 本の全体から散らして拾う
            pick = hits[::step][:6]
            print(f"## 目印：{name}（{len(hits)} 個の断章。うち {len(pick)} 個を散らして表示）\n"); [print(f"- §{n}: " + fs[:180]) for n, fs in pick]; print()
    print("（一つの断章を丸ごと読むには `--fragment <番号>`。語で探すには `--word`。）")


# ---------------- 分野の候補（題と要旨から機械的に推定）----------------
FIELDS = {
    "医学・臨床": r"\b(patients?|clinical|trial|randomi[sz]ed|cohort|therap(y|ies|eutic)|diagnos\w*|disease|treatment|hospital|mortality|surgery|surgical|prevalence|syndrome)\b",
    "薬理": r"\b(drug|dose|dosing|pharmaco\w*|efficacy|safety|agonist|antagonist|placebo|tirzepatide|antibod(y|ies))\b",
    "生物・分子": r"\b(protein|gene|genom\w*|cell(s|ular)?|molecular|DNA|RNA|transcript\w*|enzyme|mice|mouse|neuron\w*)\b",
    "心理・精神医学": r"\b(psychiatr\w*|depress\w*|anxiety|mental health|schizophreni\w*|psycholog\w*|cognit\w*|psilocybin)\b",
    "生態・環境": r"\b(species|ecolog\w*|habitat|biodiversity|climate|conservation (biology|area|status|of species)|population dynamics)\b",
    "物理・天文": r"\b(quantum|plasma|galax\w*|stellar|magnetic|equilibri\w*|particle|cosmolog\w*|spacetime)\b",
    "数学": r"\b(theorem|conjecture|lemma|proof|prime|polynomial|bound(s)?|integer)\b",
    "計算機・AI": r"\b(algorithm|neural networks?|language models?|LLMs?|machine learning|deep learning|AI|artificial intelligence|computational|attention|transformers?|gradients?|backward pass|backpropagation|training|fine-tuning|inference|tokens?|GPUs?|kernels?|BF16|FP8|FP16|FP32|optimizers?|benchmarks?|embeddings?)\b",
    "経済・経営": r"\b(econom\w*|market|firm(s)?|price(s)?|trade|labou?r|income|wage)\b",
    "社会学・政策": r"\b(sociolog\w*|inequality|social (science|theory|policy|capital|movement|network)s?|public policy|civil society|welfare state)\b",   # policy や community だけでは当てない（他分野の論文にも出る語）
    "法学": r"\b(legal|courts?|treaty|treaties|jurisdiction|statutes?|legislation|lawsuits?|international law|human rights)\b",
    "言語学": r"\b(linguistic\w*|syntax|phonolog\w*|morpholog\w*|semantic\w*|dialect\w*|grammar)\b",
    "哲学": r"\b(philosoph\w*|epistem\w*|ontolog\w*|consciousness|metaphysic\w*|skeptic\w*|scepti\w*|argue)\b",
    "宗教・神学": r"\b(theolog\w*|religio\w*|church|faith|God|biblical|scripture)\b",
    "文学・歴史": r"\b(literar\w*|novel|poetry|histor(y|ical|iography)|archive|century)\b",
    "図書館情報学": r"\b(bibliograph\w*|librar(y|ies|ianship)|documents?|information retrieval|catalog\w*)\b",
}
COI_FIELDS = {"医学・臨床", "薬理", "生物・分子", "心理・精神医学", "生態・環境"}   # 利益相反の宣言が慣例の分野

def field_candidates(title, abstract, chapter1):
    """題と要旨から分野の候補を出す。要旨が無ければ題と 1 章。題も要旨も無ければ None（利用者に返す）"""
    t, a = (title or "").strip(), (abstract or "").strip()
    if not t and not a:
        return None, "題も要旨も取れない"
    if a:
        src, basis = t + "\n" + a, ("題と要旨" if t else "要旨（題は取れない）")
    else:
        src, basis = t + "\n" + (chapter1 or ""), ("題と 1 章（要旨が取れない）" if chapter1 else "題だけ（要旨も 1 章も取れない）")
    scores = {}
    for f, pat in FIELDS.items():
        n = len(set(m.group(0).lower() for m in re.finditer(pat, src, re.I if f != "宗教・神学" else 0)))
        if n: scores[f] = n
    return sorted(scores.items(), key=lambda x: -x[1])[:3], basis

def main():
    raw, kind = fetch(sys.argv[1])
    text = html_to_text(raw) if kind == "html" else raw
    if sys.argv[1].lower().endswith(".pdf"):
        try:
            rawtext = subprocess.run(["pdftotext", "-raw", sys.argv[1], "-"], capture_output=True, text=True, timeout=180).stdout
            if len(fragments(rawtext)) > len(fragments(text)): text = rawtext
        except Exception:
            pass
    frs = fragments(text)
    if len(sys.argv) >= 4 and sys.argv[2] == "--fragment":
        n = sys.argv[3].strip().lstrip("§").rstrip(".")
        if not re.fullmatch(r"\d{1,4}(\.\d{1,4})*", n): fail("断章の番号は「43」や「1.11」の形で指定する：" + sys.argv[3])
        hit = [b for k, b in frs if k == n]
        if not hit: fail("その番号の断章が見つからない：" + n, code=1)
        print(f"§{n}: " + hit[0]); return
    if len(sys.argv) == 3 and sys.argv[2] == "--fragments":
        if len(frs) < 20: print("（番号付きの断章が見つからない）"); return
        main_fragments(frs, os.path.basename(sys.argv[1])); return
    if (len(sys.argv) == 2 or sys.argv[2:] == ["--coi-scan"]) and is_japanese(text):
        main_ja(text, sys.argv[1]); return
    if len(sys.argv) >= 4 and sys.argv[2] == "--word":
        q = sys.argv[3].lower()
        sents = ja_sentences(text) if is_japanese(text) else [x for para in re.split(r"\n\s*\n", text) for x in sentences(para)]   # 段落の切れ目をまたがない
        hits = [x for x in sents if q in x.lower()][:8]
        print("\n".join("- " + h[:300] for h in hits) if hits else "（その語の出てくる文が見つからない）"); return
    if len(sys.argv) >= 4 and sys.argv[2] == "--paragraph":
        p = find_paragraph(text, sys.argv[3])
        print(p if p else "（その語を含む段落が見つからない。--section か、語を変えて試す）"); return
    if len(sys.argv) >= 4 and sys.argv[2] in ("--section", "--chapter"):
        h, body = find_section(text, sys.argv[3], top=(sys.argv[2] == "--chapter"))
        print(f"## {h}\n\n{body}" if body else "（その語を含む節・章が見つからない）"); return
    if len(sys.argv) >= 3 and sys.argv[2] == "--abstract":
        if is_japanese(text):
            a = next((b for h, b in ja_sections(text, skip=JA_SKIP) if re.search(r"要旨|要約|概要|アブストラクト", h)), "")
        else:
            a = (struct_abstract(raw) if kind == "html" else "") or section(text, [r"^Abstract\b"], [r"^1\.?\s+Introduction", r"^I\.?\s+INTRODUCTION", r"^Introduction\b", r"^Main\s*$", r"^Background\s*$", r"^Keywords?\b"])
        print(a if a.strip() else "（要旨が見つからない）"); return
    if len(sys.argv) >= 3 and sys.argv[2] == "--conclusion":
        h, c = conclusion(text)
        note = "（結論の見出しが無いため、最後の章）" if h and not re.search(r"Conclu|Discussion|Summary|Outlook", h) else ""
        print((f"## {h}{note}\n\n" if h else "") + c if c else "（結論の章が見つからない）"); return
    title = arxiv_title(sys.argv[1])
    if not title and kind == "html":
        m = re.search(r"<article-title[^>]*>(.*?)</article-title>", raw, re.S)   # PMC の全文 XML
        if m: title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
    if not title and kind == "html":
        m = re.search(r'<h1[^>]*class="[^"]*ltx_title_document[^"]*"[^>]*>(.*?)</h1>', raw, re.S)
        if m: title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
        if not title and "<title>" in raw: title = re.search(r"<title>(.*?)</title>", raw, re.S).group(1).strip()
    title_found = bool(title)
    if not title: title = text.strip().split("\n")[0][:200]   # 表示用。分野の推定には使わない
    abstract = (struct_abstract(raw) if kind == "html" else "") or section(text, [r"^Abstract\b"], [r"^1\.?\s+Introduction", r"^I\.?\s+INTRODUCTION", r"^Introduction\b", r"^Main\s*$", r"^Background\s*$", r"^Keywords?\b"])   # I2
    intro = section(text, [r"^1\.?\s+Introduction", r"^I\.?\s+INTRODUCTION", r"^Introduction\b"],
                    INTRO_END + [r"^2\.?\s+[‘'“\"(]?[A-Z]", r"^II\.?\s+[A-Z]", r"^(Abstract|Background|Related [Ww]ork|Materials and [Mm]ethods|Methods?|Methodology|Results?|Results and [Dd]iscussion|Discussion|Conclusions?|Concluding [Rr]emarks|Limitations|Summary|Outlook|Acknowledg\w*|References|Bibliography|Appendix\w*)\s*$"])
    if not intro:   # Nature 系の JATS は導入の見出しが「Main」
        intro = section(text, [r"^Main\s*$"], INTRO_END + [r"^(Results?|Discussion|Methods?|Online content)\s*$"])
    intro = re.split(r"\n\s*\d+(\.\d+)+\.?\s+(Notation|Conventions|Preliminaries)\b[^\n]*\n", intro)[0]   # 導入の終わりの記法の小節は、導入の最後の段落にしない
    concl_head, concl = conclusion(text)
    frag_cover = sum(len(b) for n, b in frs) / max(1, len(text))
    if len(frs) >= 50 and (frag_cover > 0.5 or (not intro and not concl)):   # 本文の半分以上が番号付きの断章なら、断章の本として読む
        main_fragments(frs, title if 'title' in dir() else os.path.basename(sys.argv[1])); return
    ack = section(text, [r"^Acknowledg"], [r"^References\b", r"^Funding\b", r"^Appendix", r"^Bibliography", r"^\d+\s+[A-Z]"])[:3000]
    coi_heads = [r"^(Declarations? of (competing )?interests?|Competing (financial )?interests?|Conflicts? of interests?( statement)?|Duality of interests?)\b", r"^Disclosures?( statements?)?\b"]
    coi_found = [block_after_heading(text, [h]) for h in coi_heads]   # I3：見出しの有無と本文を分けて持つ
    coi_head_found = any(f for f, b in coi_found)
    coi_parts = [b for f, b in coi_found]
    decl = "\n".join(x for x in coi_parts if x)
    coi_first = sentences(coi_parts[0])[:2] or sentences(coi_parts[1])[:2]   # 利益相反の見出しの下の文（「None declared.」のように目印の語を含まないもの）
    coi_fallback = ""
    if not coi_head_found:   # JATS の脚注など、見出しの無い宣言の候補は、本文の後ろ 4 割から拾う（出すかは分野の候補で決める）
        coi_fallback = "\n".join(s for s in sentences(text[int(len(text) * 0.6):]) if any(re.search(p, s, re.I) for p in SPECIAL["利益相反"]))[:3000]
    chapter1 = intro
    if not chapter1:   # 導入が取れなければ、最初の番号付きの章
        m1 = re.search(r"(?m)^\s*(1|I)\.?\s+[A-Z][^\n]{1,80}\n(.*?)(?=^\s*(2|II)\.?\s+[A-Z]|\Z)", text, re.S)
        chapter1 = m1.group(2)[:6000] if m1 else ""
    fc, fc_basis = field_candidates(title if title_found else "", abstract, chapter1)
    coi_field = [f for f, n in (fc or []) if f in COI_FIELDS]
    coi_scan = len(sys.argv) >= 3 and "--coi-scan" in sys.argv[2:]
    ai_pats = [r"^(AI (use|usage|disclosure)|Use of (generative )?AI|Declaration of (generative )?AI|Generative AI|Use of large language models?)\b"]
    ai_sec = block_after_heading(text, ai_pats)[1] + "\n" + "\n".join(p for p in paragraphs(text) if any(re.match(q, p.strip(), re.I) for q in ai_pats))
    print(f"# 骨読み — {title}\n")
    if fc is None:
        print("## 分野の候補\n\n題も要旨も取れないので、分野は推定しない。分野の判断は利用者に返す。\n")
    else:
        print(f"## 分野の候補（{fc_basis}から機械的に推定。当たった語の種類の数）\n")
        print("\n".join(f"- {f}（{n}）" for f, n in fc) if fc else "- 不明（当たる語が無い）"); print()
    a = [x for x in sentences(abstract) if not re.search(r"\bDOI\b|https?://|\(\d{4}\)\.\s*[“\"]|EudraCT|ClinicalTrials\.gov|\bNCT\d|[Tt]rial [Rr]egistration|[Ss]ubject terms|^Keywords?\b|ISRCTN|PROSPERO", x)]   # 引用の書式、DOI、試験の登録番号、主題の語の行を除く
    if a: print("## 要旨の最後の二文\n"); [print("- " + s) for s in a[-2:]]; print()
    else: print("## 要旨の最後の二文\n\n（要旨が取れなかった。`--abstract` か、arXiv の要旨のページか、全文で確かめる）\n")
    ip = [x for x in paragraphs(intro) if len(x) > 150 and not re.match(r"(Figure|Fig\.|Table)\s*\d", x.strip()) and re.match(r"[A-Z‘“\"(]", x.strip()) and not any(re.match(q, x.strip(), re.I) for q in ai_pats) and re.search(r"[.!?]\s*(\d+\s*)*$", x.strip())] or paragraphs(intro)
    if ip: print("## 導入の最後の段落\n\n" + re.sub(r"\s+", " ", ip[-1])[:1200] + "\n")
    cp = [x for x in paragraphs(concl) if len(x) > 150 and not x.lstrip().startswith(("—", "-", "–")) and re.search(r"[.!?]\s*(\d+\s*)*$", x.strip())]
    if cp:
        note = f"（結論の見出しが無いため、最後の章「{concl_head}」から）" if concl_head and not re.search(r"Conclu|Discussion|Summary|Outlook", concl_head) else ""
        print("## 結論の最初の段落" + note + "\n\n" + re.sub(r"\s+", " ", cp[0])[:1200] + "\n")
        if len(cp) > 1: print("## 結論の最後の段落\n\n" + re.sub(r"\s+", " ", cp[-1])[:1200] + "\n")
    # 目印は、骨の場所（要旨・導入・結論）から先に拾う。式の多い本文の途中は拾わない（トークンの節約）
    # 導入の見出しが取れない論文（章立てが型どおりでない論文、PDF など）では、本文の頭の 2 割を導入の代わりにする
    intro_zone = intro if intro else text[: max(2000, len(text) // 5)]
    core = "\n".join([abstract, intro_zone, concl])
    body = [x for x in sentences(core) if x.count("\\") < 3] or [x for x in sentences(text) if x.count("\\") < 3]
    # 参考文献の一覧は、目印を拾う対象から外す（資料の目印が文献の URL を拾わないように）
    mref = None
    for mm in re.finditer(r"(?m)^\s*(References|Bibliography|Works [Cc]ited|Literature [Cc]ited)\s*$", text):
        if mm.start() > len(text) * 0.4: mref = mm
    body_text = text[:mref.start()] if mref else text
    full_body = [x for x in sentences(body_text) if x.count("\\") < 3]
    for name, pats in MARKERS.items():
        seen = set()   # F8：分類ごとに数える（いくつもの分類に当てはまる文は、それぞれに出す）
        hits = []
        # 論証（反論と応答）は本文の全体に散らばるので、全文から拾う
        for x in (full_body if name.startswith(("論証", "資料", "定義")) else body):
            k = re.sub(r"\W+", "", x.lower())[:200]
            if any(re.search(p, x) for p in pats) and k not in seen:
                hits.append(x); seen.add(k)
            if len(hits) >= 8: break
        if hits:
            print(f"## 目印：{name}\n"); [print("- " + s[:400]) for s in hits]; print()
    if coi_head_found and not decl:
        print("## 利益相反\n\n利益相反の見出しはあるが、その下の本文が取れなかった。原文で確かめる。\n")
    if coi_fallback and not coi_head_found:
        fb = list(dict.fromkeys(s for s in sentences(coi_fallback)))[:6]
        if coi_field or coi_scan:
            why = f"分野の候補に「{'、'.join(coi_field)}」があるので出す" if coi_field else "--coi-scan の指定で出す"
            print(f"## 利益相反（見出しの無い宣言の候補。{why}。宣言として採るかは利用者が判断する）\n"); [print("- " + x[:400]) for x in fb]; print()
        elif fc is None:
            print(f"## 利益相反（出していない。判断は利用者に）\n\n見出しの無い宣言らしい文が {len(fb)} 文あったが、題も要旨も取れず分野を推定できないので、出すかは利用者が決める。見たいときは `--coi-scan` を付ける。\n")
        else:
            print(f"## 利益相反（出していない）\n\n見出しの無い宣言らしい文が {len(fb)} 文あったが、分野の候補に、利益相反の宣言が慣例の分野が無いので出していない。見たいときは `--coi-scan` を付ける。\n")
    for name, pats in SPECIAL.items():
        if name == "利益相反" and (not coi_head_found or not decl): continue   # 見出しの無い候補と、本文の取れない見出しは上で扱った
        src = sentences(ack + "\n" + ai_sec) if name == "AIの使用" else sentences(decl or ack)
        hits = list(dict.fromkeys(s for s in src if any(re.search(p, s, re.I) for p in pats)))[:6]
        if name == "利益相反" and not hits: hits = coi_first
        if hits:
            print(f"## {name}\n"); [print("- " + s[:400]) for s in hits]; print()

if __name__ == "__main__":
    main()
