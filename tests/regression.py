#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Kokonoha
"""回帰の試験（0835版の監査 I1〜I6）。合成の入力はこのファイルの中に持っていて、ネットワークには出ない。
使い方: python3 -B tests/regression.py   （全部合格なら終了コード 0）"""
import subprocess, sys, runpy
from pathlib import Path
import tempfile
S = Path(__file__).resolve().parent.parent / "scripts" / "skeleton.py"
FIXTURES = {'nested.txt': '1 Introduction\n\nThe opening paragraph introduces the paper in detail and provides motivation.\n\n1.1 Motivation\n\nThe distinctive targetneedle occurs in this sufficiently long motivation paragraph.\n\n1.1.1 Detail\n\nThe nested detail paragraph gives a more exact statement of the motivation.\n\n1.2 Scope\n\nThis scope paragraph describes the boundaries of our work for the reader.\n\n2 Methods\n\nThe methods involve a straightforward set of procedures and careful evaluation.', 'main.xml': '<article><front><article-meta><title-group><article-title>Protein structure</article-title></title-group><abstract><p>We present a protein model. Our result is precise.</p></abstract></article-meta></front><body><sec><title>Main</title><p>We explain the background about protein structures in this full paragraph.</p></sec><sec><title>Results</title><p>We find a new structure in the experiment.</p></sec><sec><title>Discussion</title><p>The main result has useful applications.</p></sec></body><back><ref-list><title>References</title><ref>Fabricated citation text.</ref></ref-list></back></article>', 'wrapped_coi.html': '<html><title>A quantum theorem</title><body><p>Abstract</p><p>We prove a new theorem.</p><h2>Introduction</h2><p>We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. We discuss the mathematical background of this theorem in depth. </p><h2>Conflicts of interest</h2><p>The authors declare that they have\nno conflicts of interest.</p><h2>References</h2><p>One unrelated reference.</p></body></html>', 'negative.txt': 'Is the claim correct? No. We do not.', 'short_para.txt': 'Long ordinary sentence to provide context in this test.\n\nWe do not.\n\nOther ordinary sentence to provide context in this test.', 'decimal_fragments.txt': '1. First proposition.\n1.1 First subordinate proposition.\n1.11 Further subordinate proposition.\n2. Second proposition.'}
HERE = Path(tempfile.mkdtemp(prefix="skim_regression_"))
for name, body in FIXTURES.items():
    (HERE / name).write_text(body, encoding="utf-8")   # 合成の入力は、この試験の中に持っていて、走らせるたびに一時の場所へ書く
m = runpy.run_path(str(S), run_name="regression")
def run(f, *a):
    r = subprocess.run([sys.executable, "-B", str(S), str(HERE / f), *a], capture_output=True, text=True, encoding="utf-8")
    return r.stdout, r.returncode
ok = {}
c, _ = run("nested.txt", "--chapter", "targetneedle")
ok["I1 章が子節・孫節・兄弟節を含み、次章を含まない"] = "targetneedle" in c and "nested detail" in c and "scope paragraph" in c and "methods involve" not in c
sct, _ = run("nested.txt", "--section", "targetneedle")
ok["I1 節が子節を含み、兄弟節を含まない"] = "nested detail" in sct and "scope paragraph" not in sct
ok["I1 階層の深さ"] = [m["head_level"](h) for h in ["1 Introduction", "1.1 Motivation", "1.1.1 Detail"]] == [0, 1, 2]
a, _ = run("main.xml", "--abstract")
ok["I2 要旨が要素の境界で終わる"] = a.strip() == "We present a protein model. Our result is precise."
sk, _ = run("main.xml")
ok["I2 骨の要旨に参考文献が混じらない"] = "Fabricated" not in sk.split("## 導入")[0]
w, _ = run("wrapped_coi.html")
ok["I3 見出しの下の改行された宣言を出す"] = "no conflicts of interest" in w and "見出しの無い" not in w
n, _ = run("negative.txt", "--word", "No.")
ok["I4 短い否定（No.）"] = n.strip() == "- No."
ok["I4 短い日本語（未検証。保留。）"] = m["ja_sentences"]("本稿では対象を定義する。未検証。保留。") == ["本稿では対象を定義する。", "未検証。", "保留。"]
p, _ = run("short_para.txt", "--paragraph", "We do not")
ok["I5 短い段落"] = p.strip() == "We do not."
d, rc = run("decimal_fragments.txt", "--fragment", "1.1")
ok["I6 小数の断章番号"] = rc == 0 and d.strip() == "§1.1: First subordinate proposition."
bad, rc2 = run("decimal_fragments.txt", "--fragment", "x")
ok["I6 未対応の指定は説明して止まる"] = rc2 != 0
for k, v in ok.items(): print(("合格 " if v else "不合格 ") + k)
sys.exit(0 if all(ok.values()) else 1)
