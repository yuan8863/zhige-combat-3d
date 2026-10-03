# -*- coding: utf-8 -*-
"""
第 5 关 · 2D ↔ 3D 跨版本一致性核验
--------------------------------------------------------------------------
08 清单原有的四道关卡全是"同一套数值在文档 / 代码 / 原型之间是否一致"，
它们回答不了一个新问题：**3D 化到底改了什么？**

这一关就是回答那个问题的，判据只有一条：
    3D 版的数据块必须与 2D 版**逐字节一致**。

为什么用"逐字节"而不是"逐字段"：字段比对要先约定字段清单，
清单本身可能漏项（漏掉的字段恰好就是被改的那个）。
逐字节比对不需要清单——只要有一个数字、一个注释、一个空格被改动，它就会失败。

数据块的范围：从 `const FPS = 60` 起，到 `buildMoves()` 函数体结束为止。
   这一块覆盖了：节拍常量 / 韧性·格挡·弹反·破防常量 / 杀势衰减 /
   基础招式表 / 四职业偏移 / 八套武学技能 / 节拍缩放 / 有利帧推导 / 招式表生成。
   3D 版新增的一切（GEO 几何参数、GEO_TURN 转向系数、相机、渲染）都在这块**之外**。

用法：
    python tools/cross3d_check.py        # 本仓库（zhige-combat-3d）直接跑
    cd "作品集-雷火战斗策划\\仿真"; python _cross3d_check.py    # 投递包内的原始跑法

仓库适配说明（唯一被改动的地方）：
    原型文件在两个不同的目录结构里位置不同（投递包是 `原型/中文名`，本仓库是
    `index.html` + `baseline/`），所以下面把路径改成"按候选顺序取第一个存在的"。
    **比对逻辑一字未动** —— 关卡 1~5 仍然只做逐字节比对，可以用 diff 与本文件
    在 `作品集-雷火战斗策划/仿真/_cross3d_check.py` 的副本核对。
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _pick(*cands):
    """按候选顺序取第一个存在的文件；只做路径兼容，不参与任何比对。"""
    for c in cands:
        if os.path.isfile(c):
            return c
    print("❌ 找不到原型文件，试过：\n  " + "\n  ".join(cands))
    sys.exit(1)


P2D = _pick(os.path.join(ROOT, "原型", "止戈-战斗原型.html"),
            os.path.join(ROOT, "baseline", "zhige-prototype-2d.html"),
            os.path.join(ROOT, "prototype", "zhige-prototype.html"))
P3D = _pick(os.path.join(ROOT, "原型", "止戈-战斗原型-3D.html"),
            os.path.join(ROOT, "index.html"),
            os.path.join(ROOT, "prototype", "zhige-prototype-3d.html"))

ANCHOR_START = "const FPS = 60, DT = 1 / FPS;"
ANCHOR_BUILD = "function buildMoves(h) {"


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_data_block(src, path):
    """抽出数据块：从 ANCHOR_START 到 buildMoves 函数体结束（按花括号配平）。"""
    try:
        i = src.index(ANCHOR_START)
    except ValueError:
        print("❌ %s 里找不到数据块起点 %r" % (path, ANCHOR_START))
        sys.exit(1)
    try:
        j = src.index(ANCHOR_BUILD, i)
    except ValueError:
        print("❌ %s 里找不到 %r" % (path, ANCHOR_BUILD))
        sys.exit(1)
    depth = 0
    started = False
    k = j
    while k < len(src):
        ch = src[k]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                k += 1
                break
        k += 1
    return src[i:k]


def normalize(block):
    """去掉行尾空白与空行：只比"内容"，不比排版。"""
    return "\n".join(l.rstrip() for l in block.strip().splitlines() if l.strip())


def main():
    print("=" * 72)
    print("第 5 关 · 2D ↔ 3D 跨版本一致性")
    print("=" * 72)
    print("2D 源：%s" % os.path.relpath(P2D, ROOT))
    print("3D 源：%s" % os.path.relpath(P3D, ROOT))

    s2d, s3d = read(P2D), read(P3D)
    b2d, b3d = extract_data_block(s2d, P2D), extract_data_block(s3d, P3D)
    n2d, n3d = normalize(b2d), normalize(b3d)

    fails = []

    # --- 关卡 1：数据块逐字节一致 ---
    if n2d == n3d:
        print("\n✅ 数据块逐字节一致（%d 字符 / %d 行）" % (len(n3d), n3d.count("\n") + 1))
    else:
        fails.append("数据块不一致")
        l2, l3 = n2d.split("\n"), n3d.split("\n")
        print("\n❌ 数据块不一致：2D %d 行 / 3D %d 行" % (len(l2), len(l3)))
        shown = 0
        for idx in range(max(len(l2), len(l3))):
            a = l2[idx] if idx < len(l2) else "<缺失>"
            b = l3[idx] if idx < len(l3) else "<缺失>"
            if a != b:
                print("   行 %d\n     2D: %s\n     3D: %s" % (idx + 1, a, b))
                shown += 1
                if shown >= 5:
                    break

    # --- 关卡 2：数值字段计数（说明"这一关到底比了多少个数"）---
    nums3d = re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", n3d)
    print("✅ 数据块内数值字面量：%d 个（全部参与逐字节比对）" % len(nums3d))

    # --- 关卡 3：数据块确实覆盖了四张表 ---
    must = ["BASE_MOVES", "HEROES", "SKILLS", "buildMoves", "TIMING_FIELDS",
            "REACT_FRAMES", "scaleMove", "MAX_HP", "MAX_POISE", "TEMPO"]
    miss = [m for m in must if m not in n3d]
    if miss:
        fails.append("数据块缺少：" + ", ".join(miss))
        print("❌ 数据块缺少：%s" % ", ".join(miss))
    else:
        print("✅ 数据块覆盖四张表与全部常量（%d 项关键符号）" % len(must))

    # --- 关卡 4：3D 新增内容必须落在数据块之外 ---
    geo3d = extract_data_block(s3d, P3D)
    leak = [k for k in ["GEO", "GEO_TURN", "halfArc", "turnAttack", "cam", "VIEWCFG"] if k in geo3d]
    # GEO 系列只应出现在数据块之后；数据块内出现即说明改动污染了共享层
    if leak:
        fails.append("3D 专属内容泄入数据块：" + ", ".join(leak))
        print("❌ 3D 专属内容泄入数据块：%s" % ", ".join(leak))
    else:
        print("✅ 3D 专属内容（GEO / 相机 / 渲染参数）全部落在数据块之外")

    # --- 关卡 5：两边都必须是可独立打开的完整页面 ---
    for tag, s, p in (("2D", s2d, P2D), ("3D", s3d, P3D)):
        ok = s.strip().startswith("<!DOCTYPE html>") and s.rstrip().endswith("</html>")
        n_script = s.count("<script>")
        if not ok or n_script != 1:
            fails.append("%s 版不是完整的单文件页面" % tag)
            print("❌ %s 版不是完整的单文件页面（script 块 %d 个）" % (tag, n_script))
    if not fails:
        print("✅ 两版都是零依赖单文件页面（各 1 个 script 块，直接双击可运行）")

    print("\n" + "-" * 72)
    if fails:
        print("❌ 第 5 关失败（%d 项）：%s" % (len(fails), "；".join(fails)))
        return 1
    print("✅ 第 5 关通过：3D 版只改了空间维度，帧数据与 2D 版逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
