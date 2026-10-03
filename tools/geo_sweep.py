#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《止戈》3D 几何维度仿真扫描 (_geo_sweep)
========================================
原创作品 ⑨ 配套 · 黄渊 · 2027 届雷火「虚拟世界架构师（游戏战斗策划）」投递材料

本文件由 `combat_balance_sim.py` **复制**而来（原文件一字未改），只扩展"空间维度"这一层：

  维度       2D 原版（= 本文件 mode='1d' 的路径）     本文件新增（mode='3d'）
  --------   -------------------------------------   ----------------------------------
  位置       标量 x                                  (x, z) 平面
  朝向       facing ∈ {+1,-1}（每帧瞬时对准对手）       yaw（弧度），带**转向速率上限**
  命中判定   |dx| ≤ range                               hypot(dx,dz) ≤ range 且 |Δ角| ≤ halfArc
  伤害       ——                                        角度衰减 angleMul（命中：布尔量 → 连续量）
  绕背       ——                                        可选 backstabMul（攻击者处于对手背后扇区）
  移动 AI    一维趋近 / 后撤                          径向（趋近·守距）+ 切向（绕圈）分量
  闪避       前后二选一                                以攻击者为圆心的 n 个离散方位角（n→∞ 即任意角）

**纪律：帧数据、伤害、削韧、击退、杀势、韧性、连段、技能参数一律不动。**
唯一被改的是"空间维度"这一层——这正是本次验证的命题：「机制层是否与维度无关」。
mode='1d' 时本文件的行为必须与 combat_balance_sim.py **逐位一致**（用 `--parity` 自证）。

用途
----
把《止戈》战斗系统设计白皮书中的平衡主张，用蒙特卡洛方法验证。
本脚本与可玩原型 `止戈-战斗原型.html` 使用**同一套帧级规则**，
包括起手/判定/收招、有利帧、格挡硬直、架崩、韧性、破防、处决、杀势。

验证的五个命题
--------------
  P1  四职业平均胜率落在 48%~52%           → 无绝对强职业
  P2  任一 1v1 对位胜率落在 42%~58%        → 软克制（而非硬克制）
  P3  各水平段 TTK 落在目标区间            → 新手 ≤15s / 中 16~22s / 高 ≤35s
  P4  落后 60 杀势时同水平胜率 35%~42%      → 反滚雪球有效但不抹平优势
  P5  技术提升 10% 能覆盖克制优势(≤8pp)     → 技术变量 > 克制优势

运行
----
    python combat_balance_sim.py                # 默认规模（约 3 万局）
    python combat_balance_sim.py --quick        # 快速抽查
    python combat_balance_sim.py --full         # 高精度（更慢）
    python combat_balance_sim.py --seed 42 --out result.json

本文件（_geo_sweep.py）的运行方式
--------------------------------
    python _geo_sweep.py --parity                      # 自证：1D 路径与原文件逐位一致
    python _geo_sweep.py --scan base --n 500           # 2D 一维对照基线
    python _geo_sweep.py --scan s1,s2,s3 --n 500       # 三项主扫描
    python _geo_sweep.py --scan all --n 500 --out sim_geo_sweep.json

纯标准库实现，无第三方依赖。
"""

import argparse
import json
import math
import random
import sys
import time
from collections import OrderedDict

# =============================================================================
# 一、系统常量（与 01_战斗系统设计白皮书_止戈.md §3~§5 逐项对应）
# =============================================================================
FPS = 60
MAX_HP = 1200.0
MAX_POISE = 100.0
POISE_REGEN = 12.0 / FPS              # 每秒 12
POISE_REGEN_CORNERED = 18.0 / FPS     # 困兽之斗：每秒 18
BLOCK_DRAIN = 10.0 / FPS              # 格挡每秒耗韧 10
BLOCK_MAX_FRAMES = 45                 # 格挡最长 45 帧
PARRY_WINDOW = 8                      # 弹反窗口 8f（困兽 12f）
PARRY_WINDOW_CORNERED = 12
PARRY_MOMENTUM = 22                   # 弹反杀势 +22（困兽 ×1.5 → 33）
PARRY_MOMENTUM_CORNERED = 30
BLOCK_REDUCE = 0.80                   # 格挡减伤 80%
BLOCK_POISE_MULT = 0.5                # 格挡时削韧 ×0.5
GUARDCRUSH_POISE_MULT = 1.8           # 重击打中格挡时削韧 ×1.8（触发架崩）
BREAK_FRAMES = 40                     # 破防硬直 40f
EXECUTE_DMG = 300                     # 处决伤害
EXECUTE_DMG_CORNERED = 200
PARRY_POISE_CORNERED = 40              # 困兽之斗：弹反成功额外削对手 40 韧性
CORNERED_POISE_TAKEN = 0.75            # 困兽之斗：受到的削韧 ×0.75
BLOCK_REDUCE_CORNERED = 0.88           # 困兽之斗：格挡减伤 80% -> 88%（对标对方「掌控」的 +15% 伤害）
MOMENTUM_DECAY = 3.0 / FPS            # 无交战每秒衰减 3
MOMENTUM_DECAY_DELAY = 180            # 3 秒无交战才开始衰减
BLOCK_HITSTUN_LIGHT = 12              # 格挡硬直：轻档
BLOCK_HITSTUN_HEAVY = 16              # 格挡硬直：重档
GUARDCRUSH_STUN = 24                  # 架崩硬直
TEMPO = 1.0                           # 动作节拍倍率
SIDE_RULES = False                    # 慢节奏专属规则开关（贴身缠斗 / 强制近身），见 04 报告 §6.8

# =============================================================================
# 一·B、几何维度开关（本文件新增；2D 原版所有路径在 mode='1d' 下逐位不变）
# =============================================================================
# 这一整块是本次验证唯一被改动的东西。上方所有数值（帧、伤害、削韧、击退、杀势、
# 韧性、连段、技能参数）一个字都没改——命题就是「机制层是否与维度无关」。
#
# 对应 09_3D化可行性验证.md：
#   §3.1 扇形 + 胶囊体判定模型（本文件用"平面距离 + 朝向夹角"的最小可行版）
#   §3.4 AI 从一维趋近 → 趋近 / 守距 / 绕圈
#   §3.5 出招即承诺朝向（转向速率上限）—— 3D 的关键机制，不是可选项
GEO = dict(
    mode='1d',                        # '1d' = 原版一维；'3d' = 平面 + 朝向

    # ---- 命中判定（09 §3.1）----
    halfArc=math.radians(60.0),       # 扇形半角；|角度差| ≤ halfArc 才算命中
    angleFalloff=0.35,                # 角度伤害衰减：angleMul = 1 - k*(Δ角/halfArc)^1.5
                                      #   0 = 关闭（命中退回布尔量）
    edgeRatio=0.80,                   # "擦边命中"定义：Δ角/halfArc > 此值

    # ---- 绕背（09 §3.3 / §4 问题 2）----
    backstabMul=1.00,                 # 绕背伤害倍率；1.00 = 不加成
    backstabRef='rear',               # 'rear' = 攻击者位于防御者背后扇区（可触发）
                                      # 'arc'  = 任务书字面量（攻击扇形的 |Δ角| > 120°）
                                      #          —— 因 halfArc ≤ 90°，该条件恒不成立（实测触发 0 次）
    backstabAngle=math.radians(120.0),

    # ---- 转向速率上限（09 §3.5"出招即承诺朝向"）----
    turnIdle=0.10,                    # 空闲 / 移动 / 格挡：rad/帧（≈5.7°/帧 ≈ 344°/s）
    turnAttack=0.03,                  # 出招中：rad/帧（≈1.7°/帧 ≈ 103°/s）
    turnDodge=0.0,                    # 闪避中：0 = 闪避也承诺朝向（不做空中转向）
    # 硬直 / 破防一律不转向（代码里 rate=0）

    # ---- 闪避方位角（09 §4 问题 3）----
    dodgeDirs=2,                      # 可选的离散方位角数量；0 或 None = 任意角度（连续）
                                      # 2 = 正对 / 正背（= 2D 的前后二选一）

    # ---- 3D 位置 AI（09 §3.4）----
    orbitRate=dict(novice=0.15, normal=0.30, expert=0.50),   # 每次决策选择"绕圈"的概率
    orbitSmart=dict(novice=0.00, normal=0.50, expert=0.90),  # 绕圈时选"扩大对手背身角"一侧的比例
    orbitDecision=(18, 40),           # 绕圈决策间隔（帧，闭区间随机）

    # ---- 场地（3D 平面）----
    zmin=90.0, zmax=1190.0,           # z 轴边界（与 x 轴同边界 → 1100×1100 方场）

    # ---- 自证用：交换双方的处理顺序 ----
    # 一个良构的对称模型，交换顺序不应改变结果。若非对称，说明模型存在"次序依赖"，
    # 这是 3D 扩展引入的风险（2D 一维下几乎没有），必须量化后再下结论。
    orderSwap=False,
)

# 统计口径：贴身圈半径（09 §3.5"3D 下贴身是一个圆"）
CLOSE_R = 60.0

# 技术水平中文标签 → SKILL_LEVELS 的 key（3D 位置 AI 按技术档读绕圈倾向）
LEVEL_KEY = {'新手': 'novice', '中水平': 'normal', '高水平': 'expert'}

# 状态枚举（用整数以加速热循环）
S_IDLE, S_ATTACK, S_BLOCK, S_DODGE, S_HITSTUN, S_BREAK = range(6)

# =============================================================================
# 二、基础招式表（执锐 = 100% 基准）
# =============================================================================
BASE_MOVES = OrderedDict([
    # key          startup active recovery  dmg  poise  lunge hitstun blockstun knockback cancel tier  next
    ('l1',    dict(startup=6,  active=3, recovery=9,  dmg=62,  poise=14, hitstun=14,
                   blockstun=BLOCK_HITSTUN_LIGHT, cancel=4, next='l2', tier='light')),
    ('l2',    dict(startup=7,  active=3, recovery=12, dmg=78,  poise=16, hitstun=14,
                   blockstun=BLOCK_HITSTUN_LIGHT, cancel=4, next='l3', tier='light')),
    ('l3',    dict(startup=10, active=4, recovery=20, dmg=115, poise=26, hitstun=22,
                   blockstun=BLOCK_HITSTUN_HEAVY, cancel=0, next=None, tier='heavy')),
    ('heavy', dict(startup=18, active=5, recovery=24, dmg=185, poise=38, hitstun=22,
                   blockstun=GUARDCRUSH_STUN, cancel=0, next=None, tier='heavy',
                   guardCrush=True)),
    ('launch',dict(startup=12, active=4, recovery=20, dmg=95,  poise=20, hitstun=24,
                   blockstun=BLOCK_HITSTUN_HEAVY, cancel=0, next=None, tier='heavy')),
    ('ult',   dict(startup=24, active=6, recovery=30, dmg=380, poise=100, hitstun=30,
                   blockstun=GUARDCRUSH_STUN, cancel=0, next=None, tier='ult',
                   armor=True, guardCrush=True)),
])

# =============================================================================
# 三、四职业（偏移值取自 03_英雄技能设计集_止戈.md）
#    速度纪律（v1.1）：移速 run 拉开成清晰梯度，且位次必须与攻速（轻击起手）**完全同向**：
#      影梭 370/5f  >  执锐 280/6f  >  长策 255/8f  >  重锋 235/10f
#    （极差 36%）。"快"是一个能感觉到的身份，而不是被「碾压」档的移速 ×1.12 一冲就抹平的装饰；
#    两条梯度不同向会造成含糊的职业身份，_verify.py 与原型端核验脚本都会直接判失败。
#    原型（止戈-战斗原型.html）与本文件必须同步修改。
# =============================================================================
HEROES = OrderedDict([
    ('zhirui', dict(name='执锐', dmgScale=1.00, poiseScale=1.00, startupOffset=0,
                    range=140, walk=155, run=290, invulnFrames=8,
                    armorFrom=None, closePenalty=None, ult=None)),
    ('zhongfeng', dict(name='重锋', dmgScale=1.18, poiseScale=1.44, startupOffset=4,
                       range=175, walk=135, run=255, invulnFrames=8,
                       armorFrom=8, closePenalty=None, knockbackScale=1.15,
                       ult=dict(name='绝技·崩山', startup=28, active=6, recovery=32,
                                dmg=470, poise=150, hitstun=30,
                                blockstun=GUARDCRUSH_STUN, guardCrush=True, armor=True))),
    ('yingsuo', dict(name='影梭', dmgScale=0.82, poiseScale=0.80, startupOffset=-1,
                     range=115, walk=175, run=330, invulnFrames=10,
                     armorFrom=None, closePenalty=None, knockbackScale=0.85,
                     ult=dict(name='绝技·千影', startup=20, active=18, recovery=30,
                              dmg=62, poise=15, hitstun=8, blockstun=8,
                              hits=6, hitInterval=3, knockback=6))),
    ('changce', dict(name='长策', dmgScale=0.92, poiseScale=0.96, startupOffset=2,
                     range=225, walk=145, run=275, invulnFrames=8,
                     armorFrom=None, closePenalty=(70, 0.60), knockbackScale=1.70,
                     # v1.4 贴身缠斗规则：长策的判定区最长，被贴身缠斗时按 rate 秒流失韧性，
                     # 兵刃脱手（韧性归零）后进入"距离优势失效"状态——见 04 报告 §6.8
                     closeAttrition=dict(range=85, delay=60, drain=14.0, poiseScale=0.55, rangeScale=0.62,
                                         dmgScale=0.70, knockbackScale=0.35),
                     ult=dict(name='绝技·千里', startup=26, active=5, recovery=34,
                              dmg=350, poise=60, hitstun=30,
                              blockstun=GUARDCRUSH_STUN))),
])


# =============================================================================
# 三·B、武学技能（每职业 2 个，与原型 SKILLS 逐字段一致）
# =============================================================================
# dashTo        位移量（正=向前，负=向后）
# invuln        无敌帧窗口 [起, 止]（相对招式帧）
# counter       反击架势 {dmg, poise, hitstun}
# armorStance   架势窗口内免僵直
# buffNext      架势生效时给"下一次攻击"的伤害倍率
# rangeMult     攻击距离倍率
# landing       落地冲击 {frame, radius, dmg, knockback}
# zone          部署场域 {dist, radius, duration, dps, slow}
SKILLS = {
    '执锐': [
        # 踏雪 = 纯位移（180px 前突 + 无敌 6~13f）——这是 v1.3 定稿、也是默认节拍 12/12 平衡的一部分。
        #   v1.5 曾在"方案 B"里把它升级为中距离「突进斩」（判定 ×1.15 + 90 伤害），
        #   实测该改动会把默认节拍打破（执锐 49% → 74%），因此**回滚**；
        #   探索过程与结论保留在 04 报告 §6.8，未采用。
        #   no_kb 由 SIDE_RULES 门控（默认关闭，仅慢节拍探索分支使用）。
        dict(name='踏雪', type='dash', cd=360, startup=5, active=8, recovery=11,
             dashTo=180, invuln=(6, 13), no_kb=60),
        dict(name='回风', type='stance', cd=540, startup=4, active=20, recovery=6,
             counter=dict(dmg=140, poise=30, hitstun=22)),
    ],
    '重锋': [
        dict(name='镇岳', type='buff', cd=600, startup=12, active=15, recovery=8,
             armorStance=True, buffNext=1.40),
        dict(name='荡寇', type='aoe', cd=420, startup=20, active=6, recovery=26,
             dmg=150, poise=45, hitstun=22, blockstun=16, knockback=130, rangeMult=1.80),
    ],
    '影梭': [
        dict(name='影步', type='blink', cd=300, startup=2, active=4, recovery=0,
             dashTo=200, invuln=(1, 6), no_kb=50),   # v1.4 影梭：瞬移后 50 帧内不被击退推开（贴脸骚扰的资本）
        dict(name='连环刺', type='multi', cd=480, startup=4, active=27, recovery=6,
             dmg=45, poise=12, hitstun=10, blockstun=8, knockback=20,
             hits=3, hitInterval=9),
    ],
    '长策': [
        dict(name='横驱', type='retreat', cd=420, startup=8, active=12, recovery=10,
             dashTo=-160, landing=dict(frame=22, radius=240, dmg=60, knockback=120)),
        dict(name='枪阵', type='deploy', cd=720, startup=18, active=0, recovery=10,
             zone=dict(dist=150, radius=170, duration=480, dps=50, slow=0.35)),
    ],
}


def skill_kind(m):
    """技能按用途分类，决定 AI 什么时候该放它（与原型 aiSkillKind 一致）"""
    if m.get('counter') or m.get('armorStance'):
        return 'defensive'      # 回风 / 镇岳
    if m.get('zone') or m.get('landing'):
        return 'control'        # 枪阵 / 横驱
    if m.get('hits', 1) > 1 or m.get('rangeMult'):
        return 'offensive'      # 连环刺 / 荡寇
    return 'mobility'           # 踏雪 / 影步


def build_moves(h, tempo=1.0):
    """由基础招式 + 职业偏移生成完整招式表（与原型 buildMoves 完全一致）

    tempo：动作节拍倍率（v1.3 引入）。1.0 = 原速；2.0 = 起手/判定/收招/僵直/取消窗口全部 ×2。
           注意**只放大时间轴，不放大伤害**——所以 tempo>1 时 TTK 会显著变长，
           这是有意的：把"攻速"从一个隐藏变量变成可被玩家读到的设计旋钮（详见 09 文档）。
    """
    out = {}
    for k, b in BASE_MOVES.items():
        m = dict(b)
        if k == 'ult' and h['ult']:
            m.update(h['ult'])
        else:
            m['startup'] = b['startup'] + h['startupOffset']
            m['dmg'] = round(b['dmg'] * h['dmgScale'])
            m['poise'] = round(b['poise'] * h['poiseScale'])
        m.setdefault('hits', 1)
        m.setdefault('hitInterval', 1)
        m.setdefault('guardCrush', False)
        m.setdefault('armor', False)
        if tempo != 1.0:
            # 时间轴整体缩放（含判定/收招/僵直/取消窗口/多段间隔）；伤害、削韧、位移都不变。
            # 说明：职业级的 startupOffset 与 armorFrom 属于"数据字段"，
            # 由传参方（校验脚本、烘焙器）负责按节拍换算；这里只缩放招式自身的时间字段，
            # 避免"缩放两次"（已经踩过一次，详见 04 报告 §6.6）。
            for f in ('startup', 'active', 'recovery', 'hitstun', 'blockstun', 'cancel', 'hitInterval'):
                if f in m and isinstance(m[f], (int, float)):
                    m[f] = max(1, int(round(m[f] * tempo))) if f != 'cancel' else int(round(m[f] * tempo))
        m['total'] = m['startup'] + m['active'] + m['recovery']
        # 有利帧 = 受击僵直/格挡硬直 − (总帧 − 起手)；active+recovery 恒定 → 跨职业不变
        m['advHit'] = m['hitstun'] - (m['active'] + m['recovery'])
        m['advBlock'] = m['blockstun'] - (m['active'] + m['recovery'])
        out[k] = m
    # 武学技能：与原型 SKILLS 逐字段一致
    for i, s in enumerate(SKILLS.get(h['name'], [])):
        m = dict(dmg=0, poise=0, hitstun=14, blockstun=12, knockback=0,
                 lunge=0, cancel=0, hits=1, hitInterval=1, tier='skill',
                 guardCrush=False, armor=False)
        m.update(s)
        m['key'] = 's%d' % (i + 1)
        if tempo != 1.0:
            for f in ('startup', 'active', 'recovery', 'hitstun', 'blockstun', 'cancel', 'hitInterval'):
                if f in m and isinstance(m[f], (int, float)):
                    m[f] = max(1, int(round(m[f] * tempo))) if f != 'cancel' else int(round(m[f] * tempo))
        m['total'] = m['startup'] + m['active'] + m['recovery']
        m['advHit'] = m['hitstun'] - (m['active'] + m['recovery'])
        m['advBlock'] = m['blockstun'] - (m['active'] + m['recovery'])
        out[m['key']] = m
    return out


# =============================================================================
# 四、技术水平（Skill Profile）
# =============================================================================
# reaction     : 对敌方起手做出防守决策所需帧数（越小越强）
# block_rate   : 反应后选择格挡（并期望吃到弹反窗口）的比例
# dodge_rate   : 选择闪避的比例
# trade_rate   : 选择抢帧（同时出招）的比例
# aggression   : 在攻击距离内主动进攻的倾向（★ 随技术水平【下降】：高手更耐心）
# regroup_poise: 韧性低于此值时主动退避重整（★ 随技术水平【上升】：高手会管理风险）
# combo_rate   : 命中后继续接续连段的纪律性
SKILL_LEVELS = {
    'novice': dict(label='新手', reaction=22, block_rate=0.18, dodge_rate=0.05,
                   trade_rate=0.06, aggression=0.62, combo_rate=0.35,
                   punish_rate=0.10, crush_rate=0.08, predict_rate=0.05, skill_rate=0.35,
                   regroup_poise=0.0, tempo=0.30),
    'normal': dict(label='中水平', reaction=14, block_rate=0.44, dodge_rate=0.15,
                   trade_rate=0.14, aggression=0.48, combo_rate=0.62,
                   punish_rate=0.28, crush_rate=0.22, predict_rate=0.20, skill_rate=0.70,
                   regroup_poise=28.0, tempo=0.85),
    'expert': dict(label='高水平', reaction=9, block_rate=0.62, dodge_rate=0.24,
                   trade_rate=0.22, aggression=0.36, combo_rate=0.82,
                   punish_rate=0.48, crush_rate=0.40, predict_rate=0.36, skill_rate=1.00,
                   regroup_poise=50.0, tempo=1.40),
}


def shift_skill(base, delta):
    """技术整体上浮 delta（0.10 = 10%）——用于验证『技术变量能否覆盖克制优势』"""
    s = dict(base)
    s['reaction'] = max(4, int(round(base['reaction'] * (1 - delta))))
    s['block_rate'] = min(0.92, base['block_rate'] * (1 + delta))
    s['dodge_rate'] = min(0.55, base['dodge_rate'] * (1 + delta))
    s['trade_rate'] = min(0.45, base['trade_rate'] * (1 + delta))
    s['combo_rate'] = min(0.97, base['combo_rate'] * (1 + delta))
    s['aggression'] = min(0.85, base['aggression'] * (1 + delta))
    s['punish_rate'] = min(0.80, base['punish_rate'] * (1 + delta))
    s['crush_rate'] = min(0.70, base['crush_rate'] * (1 + delta))
    s['predict_rate'] = min(0.65, base['predict_rate'] * (1 + delta))
    s['skill_rate'] = min(1.0, base['skill_rate'] * (1 + delta))
    s['regroup_poise'] = min(72.0, base['regroup_poise'] * (1 + delta))
    s['tempo'] = min(2.2, base['tempo'] * (1 + delta))
    return s


# =============================================================================
# 五、战士
# =============================================================================
class Fighter(object):
    __slots__ = ('h', 'moves', 'sk', 'x', 'facing', 'hp', 'poise', 'state',
                 'move', 'mf', 'hitseg', 'lasthit', 'stun', 'blockf', 'parry_until',
                 'block_until', 'dodgef', 'dodge_dir', 'movedir', 'thinkcd',
                 'invuln_until', 'threat_at', 'threat_move', 'threat_seen',
                 'buf_move', 'buf_at', 'is_p', 'armored',
                 'cd', 'stance', 'next_atk_mult', 'pressed_frames', 'attr_suppress', '_drop_logged', 'no_kb_until',
                 # ---- 3D 几何维度新增字段（2D 路径下全部保持中性值）----
                 'z', 'yaw', 'dodge_yaw', 'orbit', 'orbit_side', 'orbit_next',
                 '_atk_open', '_atk_contact', '_atk_dodged', '_atk_rear')

    def __init__(self, hero_key, skill, x, facing, is_p, z=0.0):
        self.h = HEROES[hero_key]
        self.moves = build_moves(self.h, TEMPO)
        self.sk = skill
        self.x = float(x)
        self.z = float(z)
        self.facing = facing
        # 3D：朝向用弧度表示；初始由 simulate 依据双方相对位置设定
        self.yaw = 0.0 if facing >= 0 else math.pi
        self.is_p = is_p
        self.reset()

    def reset(self):
        self.hp = MAX_HP
        self.poise = MAX_POISE
        self.state = S_IDLE
        self.move = None
        self.mf = 0
        self.hitseg = 0
        self.lasthit = -99
        self.stun = 0
        self.blockf = 0
        self.parry_until = -999
        self.block_until = -999
        self.dodgef = 0
        self.dodge_dir = -1
        self.movedir = 0
        self.thinkcd = 0
        self.invuln_until = -999
        self.threat_at = -9999
        self.threat_move = None
        self.threat_seen = None
        self.buf_move = None
        self.buf_at = -9999
        self.cd = {}                 # 技能冷却剩余帧
        self.stance = None           # 当前生效的架势（反击 / 霸体）
        self.next_atk_mult = 1.0     # 镇岳：下一次攻击伤害倍率
        self.armored = False
        self._drop_logged = False
        # v1.4 贴身缠斗规则：连续被贴身缠斗的帧数（只有"有身位劣势"的职业会累积）
        self.pressed_frames = 0
        self.attr_suppress = False
        self.no_kb_until = -1
        # ---- 3D 几何维度新增状态 ----
        self.dodge_yaw = 0.0          # 3D 闪避的方位角（弧度）
        self.orbit = 0               # 切向移动意图 ∈ {-1,0,+1}
        self.orbit_side = 0
        self.orbit_next = 0          # 下一次绕圈决策的帧号
        self._atk_open = False       # 本次攻击是否已进入判定窗口（用于空挥率统计）
        self._atk_contact = False    # 判定窗口内是否出现过"几何上可命中"
        self._atk_dodged = False     # 是否被无敌帧躲掉
        self._atk_rear = False       # 进入判定窗口时是否处于对手背后扇区

    # --- 由杀势推导的增益 ---
    def mods(self, momentum):
        a = momentum if self.is_p else -momentum
        if a >= 90:
            return 1.25, 1.12, 1.20
        if a >= 60:
            return 1.15, 1.08, 1.15
        if a >= 30:
            return 1.08, 1.04, 1.10
        return 1.00, 1.00, 1.00

    def cornered(self, momentum):
        a = momentum if self.is_p else -momentum
        return a <= -60

    def dominant(self, momentum):
        a = momentum if self.is_p else -momentum
        return a >= 60

    def parry_win(self, momentum):
        return PARRY_WINDOW_CORNERED if self.cornered(momentum) else PARRY_WINDOW

    def can_act(self):
        if self.state in (S_IDLE, S_BLOCK):
            return True
        if self.state == S_ATTACK and self.move and self.mf >= self.move['startup'] + self.move['active'] \
                and self.move['cancel'] > 0 and self.hitseg > 0:
            return True
        return False


# =============================================================================
# 六、单局仿真
# =============================================================================
def ang_diff(a, b):
    """两个绝对方位角之间的最短弧差，返回 [0, π]（弧度）

    09 文档 §4 要求"|角度差| 取最短弧"——否则 179° 与 -179° 的差会被算成 358°，
    站在对手正后方反而变成"最不可能被命中"。
    """
    d = (a - b) % (2.0 * math.pi)
    if d > math.pi:
        d = 2.0 * math.pi - d
    return d


def turn_toward(cur, target, rate):
    """把朝向 cur 以不超过 rate 的步长转向 target（走最短弧）

    这是 3D 的关键机制"出招即承诺朝向"的载体：2D 版 facing 每帧瞬时对准对手
    （等于转向速率无限大），3D 版必须给出上限，否则朝向永远正确、绕背永不成立。
    """
    if rate <= 0.0:
        return cur
    d = (target - cur + math.pi) % (2.0 * math.pi) - math.pi
    if d > rate:
        d = rate
    elif d < -rate:
        d = -rate
    return (cur + d) % (2.0 * math.pi)


def geo_dist(a, b):
    """平面距离（2D 版是 abs(a.x-b.x)；3D 版是 √(dx²+dz²)）"""
    return math.hypot(a.x - b.x, a.z - b.z)


def rear_angle(att, dfn):
    """攻击者相对「防御者背后」的角度：0 = 正好在正面，π = 正好在背后"""
    bearing = math.atan2(att.z - dfn.z, att.x - dfn.x)
    return ang_diff(bearing, dfn.yaw)


def eff_range(f):
    """当前有效判定距离。
    v1.4「兵刃脱手」：韧性被打空的长兵职业判定距离暂时缩短（closeAttrition.rangeScale），
    这样"永动风筝"就有了可被破解的窗口——短手职业追上去、打空韧性、距离优势失效。"""
    ca = f.h.get('closeAttrition') if SIDE_RULES else None
    if ca and f.poise <= 0.0:
        return f.h['range'] * ca.get('rangeScale', 1.0)
    return f.h['range']


def simulate(a_key, b_key, a_skill, b_skill, rng, momentum0=0.0, max_frames=60 * 240,
             a_x=440.0, b_x=840.0, a_z=0.0, b_z=0.0):
    """返回 (赢家 'A'/'B'/'draw', 帧数, 统计字典)

    a_x / b_x 可指定起始站位，用于验证「墙面惩罚」（白皮书 §8.2）：
    把一方放在靠近左右墙的位置，观察贴墙是否真的构成劣势。
    a_z / b_z 为 3D 模式的纵深坐标（mode='1d' 时被忽略，战斗完全在 z=0 的一维上进行）。
    """
    # ---- 几何配置快照（每次调用读取，便于逐格扫描而不必重载模块）----
    g_mode = GEO['mode']
    g_3d = (g_mode == '3d')
    g_half = GEO['halfArc']
    g_fall = GEO['angleFalloff'] if g_3d else 0.0
    g_edge = GEO['edgeRatio']
    g_back = GEO['backstabMul'] if g_3d else 1.0
    g_backref = GEO['backstabRef']
    g_backang = GEO['backstabAngle']
    g_turn_idle = GEO['turnIdle']
    g_turn_atk = GEO['turnAttack']
    g_turn_dodge = GEO['turnDodge']
    g_dodge_dirs = GEO['dodgeDirs']
    g_zmin = GEO['zmin']
    g_zmax = GEO['zmax']
    g_orbit_rate = GEO['orbitRate']
    g_orbit_smart = GEO['orbitSmart']
    g_orbit_dec = GEO['orbitDecision']

    A = Fighter(a_key, a_skill, float(a_x), 1, True, z=float(a_z))
    B = Fighter(b_key, b_skill, float(b_x), -1, False, z=float(b_z))
    # 处理顺序（自证用）：orderSwap=True 时把 A/B 在各类循环里的先后互换
    if GEO.get('orderSwap'):
        seq = (B, A)
        seq2 = ((B, A), (A, B))
    else:
        seq = (A, B)
        seq2 = ((A, B), (B, A))
    if g_3d:
        # 初始朝向：双方互相对位（与 2D 的 facing=+1/-1 等价）
        A.yaw = math.atan2(B.z - A.z, B.x - A.x)
        B.yaw = (A.yaw + math.pi) % (2.0 * math.pi)
    momentum = float(momentum0)
    last_combat = -99999

    st = dict(hits=0, blocks=0, dodges=0, parries=0, breaks=0, execs=0,
              ults=0, whiffs=0, counters=0, skills=0, a_dmg=0.0, b_dmg=0.0,
              # ---- 几何维度统计（2D 路径同样记录，便于与 3D 同口径对比）----
              frames=0, close_frames=0,
              atk_inst=0, whiff_geo=0, whiff_dodge=0,
              contacts=0, edge_hits=0, rear_contacts=0, ang_sum=0.0,
              rear_inst=0, rear_inst_hit=0,
              close_contacts=0, close_atk_inst=0,
              dodge_used=0, backstab_hits=0,
              first_att='', first_close=0, first_dist=0.0)
    zones = []          # 部署场域（长策「枪阵」）

    def finish_atk(f):
        """结算一次"进入过判定窗口的攻击"——空挥率统计的分母就在这里"""
        if not f._atk_open:
            return
        f._atk_open = False
        st['atk_inst'] += 1
        if f._atk_rear:
            st['rear_inst'] += 1
            if f._atk_contact:
                st['rear_inst_hit'] += 1
        if not f._atk_contact:
            st['whiff_geo'] += 1
        elif f._atk_dodged:
            st['whiff_dodge'] += 1

    def start_move(f, key, frame):
        m = f.moves[key]
        if m.get('cd'):                       # 技能：冷却未好则拒绝
            if f.cd.get(key, 0) > 0:
                return False
            f.cd[key] = m['cd']
        finish_atk(f)                         # 上一招若被打断，先按"已发生过"结算
        f._atk_contact = False
        f._atk_dodged = False
        f._atk_rear = False
        f.move = m
        f.mf = 0
        f.hitseg = 0
        f.lasthit = -99
        f.state = S_ATTACK
        if key == 'ult':
            nonlocal momentum
            momentum += -60.0 if f.is_p else 60.0
        if m.get('buffNext'):
            f.next_atk_mult = m['buffNext']
        return True

    def receive_hit(att, dfn, m, blocked, parried, frame, ad=0.0, rear=False):
        """ad   = 本次命中的 |朝向夹角|（弧度；1D 模式下恒为 0 → 不参与任何计算）
        rear = 本次命中时攻击者是否处于防御者背后扇区（3D 专属）"""
        nonlocal momentum, last_combat
        last_combat = frame

        # --- 反击架势（执锐「回风」）：架势窗口内受击 → 自动反击 ---
        if dfn.stance and dfn.stance.get('counter'):
            c = dfn.stance['counter']
            att.hp = max(0.0, att.hp - c['dmg'])
            att.poise = max(0.0, att.poise - c['poise'])
            finish_atk(att)
            att.state = S_HITSTUN
            att.stun = c['hitstun']
            att.move = None
            att.hitseg = 0
            dfn.stance = None
            momentum += 12.0 if dfn.is_p else -12.0
            st['counters'] += 1
            return

        # --- 弹反 ---
        if parried:
            st['parries'] += 1
            gain = PARRY_MOMENTUM_CORNERED if dfn.cornered(momentum) else PARRY_MOMENTUM
            momentum += gain if dfn.is_p else -gain
            finish_atk(att)
            att.state = S_HITSTUN
            att.stun = 22
            att.move = None
            att.hitseg = 0
            # 困兽之斗：弹反附带削韧，让弹反成为真正的翻盘引擎
            if dfn.cornered(momentum):
                att.poise = max(0.0, att.poise - PARRY_POISE_CORNERED)
            return

        # --- 破防中：处决 ---
        if dfn.state == S_BREAK:
            ex = EXECUTE_DMG_CORNERED if dfn.cornered(momentum) else EXECUTE_DMG
            dfn.hp = max(0.0, dfn.hp - ex)
            dfn.stun = 0
            dfn.state = S_IDLE
            dfn.poise = MAX_POISE * 0.30
            st['execs'] += 1
            if att.is_p:
                st['a_dmg'] += ex
            else:
                st['b_dmg'] += ex
            return

        dmg_m, spd_m, poise_m = att.mods(momentum)
        dmg = m['dmg'] * dmg_m
        if m is att.moves['l2']:
            dmg *= 0.95
        elif m is att.moves['l3']:
            dmg *= 0.90
        # 镇岳增益：下一次基础攻击 ×1.4，用后即消耗
        if att.next_atk_mult > 1.0 and m['tier'] != 'skill':
            dmg *= att.next_atk_mult
            att.next_atk_mult = 1.0
        cp = att.h['closePenalty']
        # 「距离」的定义随维度改变：2D 是一维差值，3D 是平面距离（贴身惩罚 = 一个圆）
        if cp and ((geo_dist(att, dfn) if g_3d else abs(att.x - dfn.x)) < cp[0]):
            dmg *= cp[1]
        pd = m['poise'] * poise_m
        # ---- 3D 角度伤害衰减：把"命中"从布尔量变成连续量（09 §3.1 的核心推论）----
        # angleMul = 1 - angleFalloff * (|Δ角| / halfArc)^1.5
        if g_fall > 0.0 and g_half > 0.0:
            am = 1.0 - g_fall * (min(1.0, ad / g_half) ** 1.5)
            if am < 0.0:
                am = 0.0
            dmg *= am
            pd *= am
        # ---- 3D 可选绕背加成（09 §3.3 / §4 问题 2）----
        if rear and g_back != 1.0:
            dmg *= g_back
            pd *= g_back
            st['backstab_hits'] += 1
        # v1.4「兵刃脱手」：贴身缠斗把长兵职业的韧性打空后，攻击距离优势暂时失效
        # （判定距离缩短、伤害与击退下降）——这是对"永动风筝"的机制级反制
        drop = (SIDE_RULES and att.h.get('closeAttrition') is not None and att.poise <= 0.0)
        if drop and not getattr(att, '_drop_logged', False):
            st['drops'] = st.get('drops', 0) + 1
            att._drop_logged = True
        if drop:
            dmg *= att.h['closeAttrition']['dmgScale']
            pd *= att.h['closeAttrition']['poiseScale']
        elif att.h.get('closeAttrition') is not None:
            att._drop_logged = False
        # 困兽之斗：连续型防守补偿——切断「被压制 → 破防 → 处决」的雪球链条
        if dfn.cornered(momentum):
            pd *= CORNERED_POISE_TAKEN
        if blocked:
            br = BLOCK_REDUCE_CORNERED if dfn.cornered(momentum) else BLOCK_REDUCE
            dmg *= (1.0 - br)
            pd *= GUARDCRUSH_POISE_MULT if m['guardCrush'] else BLOCK_POISE_MULT
            st['blocks'] += 1
        else:
            st['hits'] += 1

        dfn.hp = max(0.0, dfn.hp - dmg)
        dfn.poise = max(0.0, dfn.poise - pd)
        if att.is_p:
            st['a_dmg'] += dmg
        else:
            st['b_dmg'] += dmg

        # --- 杀势 ---
        if blocked:
            mg = 3
        elif m['hits'] > 1:
            mg = 3
        elif m['tier'] == 'ult':
            mg = 14
        elif m['tier'] == 'heavy' and m is att.moves['heavy']:
            mg = 10
        elif m is att.moves['launch']:
            mg = 7
        else:
            mg = 6
        momentum += mg if att.is_p else -mg

        # --- 硬直（霸体：吸收轻档攻击的僵直） ---
        armor_holds = dfn.armored and m['tier'] == 'light'
        if armor_holds:
            pass                                  # 掉血掉韧，但不进入硬直
        elif blocked and m['guardCrush']:
            finish_atk(dfn)
            dfn.state = S_HITSTUN
            dfn.stun = GUARDCRUSH_STUN
            dfn.blockf = 0
        else:
            finish_atk(dfn)
            dfn.state = S_HITSTUN
            dfn.stun = m['blockstun'] if blocked else m['hitstun']
        if not blocked and not armor_holds:
            # v1.4 强制近身：防御方处于"无视击退"窗口时不吃位移（但仍吃伤害与削韧）
            if not (SIDE_RULES and frame <= getattr(dfn, 'no_kb_until', -1)):
                kb = m.get('knockback', 0) * att.h.get('knockbackScale', 1.0)
                # 击退量不变，只把方向从"一维符号"换成"朝向向量"（空间层改动）
                if g_3d:
                    dfn.x += kb * math.cos(att.yaw)
                    dfn.z += kb * math.sin(att.yaw)
                else:
                    dfn.x += kb * att.facing

        # --- 韧性归零 → 破防 ---
        if dfn.poise <= 0 and dfn.state != S_BREAK:
            finish_atk(dfn)
            dfn.state = S_BREAK
            dfn.stun = BREAK_FRAMES
            dfn.move = None
            st['breaks'] += 1

    for frame in range(1, max_frames + 1):
        # ---------- v1.4 贴身缠斗规则（Close-range Attrition） ----------
        # 规则：两个判定圈重叠（贴身）时，**判定距离更长的那个职业**持续流失韧性。
        # 为什么这样设计（节拍 ×2 配平的核心结论，见 04 报告 §6.8）：
        #   时间轴翻倍后所有攻击都变得可读 → 防守成功率上升 → 胜负由"能否在防守中换取位置"决定；
        #   而"长判定区 + 击退"是位置博弈的最强工具，于是出现永动风筝（长策对执锐 80~90%）。
        #   数值补偿全部无效（11 组实测），所以必须给"距离优势"本身加一条成本：
        #   把对手挡在判定区外侧是收益，但被贴身缠住就是代价。
        #   这让短手职业第一次拥有"追上去就有回报"的确定性目标。
        for me, opp in seq2:
            # 规则只在"慢节拍"下启用：tempo 1.0 的平衡表已经 12/12 达标，不需要它；
            # 它是为 tempo ≥ 1.5 时"距离价值被抬高"设计的反制，见 04 报告 §6.8。
            em = me.h.get('closeAttrition') if SIDE_RULES else None
            if not em:
                me.pressed_frames = 0
                me.attr_suppress = False
                continue
            gap = geo_dist(me, opp) if g_3d else abs(opp.x - me.x)
            reach = em['range']           # 被贴身判定的距离阈值
            if gap <= reach:
                me.pressed_frames += 1
                if me.pressed_frames >= em['delay']:
                    # 缠斗期间**压掉常规韧性回复**：tempo 2.0 下 POISE_REGEN 是 24/s，
                    # 而 drain 只有 8/s——不抑制回复的话流失被完全淹没，规则等于不存在。
                    # （第一版实现就踩了这个坑：六档参数跑出来一字不差。）
                    me.attr_suppress = True
                    me.poise = max(0.0, me.poise - em['drain'] / FPS)
                else:
                    me.attr_suppress = False
            else:
                me.attr_suppress = False
                me.pressed_frames = max(0, me.pressed_frames - 2)   # 脱离得比累积慢，鼓励真的走开

        # ---------- 决策 ----------
        for me, opp in seq2:
            if me.stun > 0 or me.state in (S_HITSTUN, S_BREAK):
                me.threat_move = None
                continue
            dist = geo_dist(me, opp) if g_3d else abs(opp.x - me.x)
            dirto = 1 if opp.x > me.x else -1
            my_range = eff_range(me)

            # --- 移动意图：每帧刷新（格挡中也可缓慢推进，否则远程压制无解） ---
            if me.state in (S_IDLE, S_BLOCK):
                if me.poise < me.sk['regroup_poise'] and dist < my_range * 1.6:
                    # 退避重整：韧性见底先拉开距离等回复——这是"高手防守更好"的行为载体
                    me.movedir = -dirto
                elif dist > my_range * 0.85:
                    me.movedir = dirto
                elif dist < my_range * 0.70 and me.h['closePenalty']:
                    # 空间控制型：必须把对手挡在"我能打到你、你打不到我"的距离带里
                    me.movedir = -dirto
                else:
                    me.movedir = 0
            else:
                me.movedir = 0

            # --- 3D 位置行为③：绕圈（改变方位角，取得对手的侧后角度）---
            # 2D 的"左右横移"在 3D 里就是切向移动，而切向移动是"绕背"的唯一手段。
            # 守距 / 趋近 是径向（movedir），绕圈是切向（orbit），二者正交合成。
            if g_3d:
                me.orbit = 0
                if me.state in (S_IDLE, S_BLOCK):
                    if frame >= me.orbit_next:
                        me.orbit_next = frame + rng.randint(g_orbit_dec[0], g_orbit_dec[1])
                        lv = LEVEL_KEY.get(me.sk['label'], 'normal')
                        if dist <= my_range * 1.35 and rng.random() < g_orbit_rate[lv]:
                            # 切向二选一：高手挑"把对手背身角撑大"的一侧，新手随机
                            if dist > 1e-6:
                                ux = (me.x - opp.x) / dist
                                uz = (me.z - opp.z) / dist
                            else:
                                ux, uz = 1.0, 0.0
                            cand = []
                            for s in (1, -1):
                                nx = me.x + s * (-uz) * 8.0
                                nz = me.z + s * ux * 8.0
                                cand.append((ang_diff(math.atan2(nz - opp.z, nx - opp.x), opp.yaw), s))
                            if rng.random() < g_orbit_smart[lv]:
                                me.orbit_side = cand[0][1] if cand[0][0] >= cand[1][0] else cand[1][1]
                            else:
                                me.orbit_side = 1 if rng.random() < 0.5 else -1
                        else:
                            me.orbit_side = 0
                    me.orbit = me.orbit_side
                else:
                    me.orbit = 0

            opp_atk = opp.state == S_ATTACK and opp.move
            opp_startup = bool(opp_atk and opp.mf <= opp.move['startup'])
            opp_recover = bool(opp_atk and opp.mf > opp.move['startup'] + opp.move['active'])

            # 威胁识别（仅起手阶段构成威胁）
            if opp_startup and dist <= eff_range(opp) + 16:
                tag = (opp.mf, id(opp.move))
                if me.threat_seen != tag:
                    me.threat_seen = tag
                    me.threat_at = frame
                    me.threat_move = opp.move
            elif not opp_atk:
                me.threat_move = None
                me.threat_seen = None

            # 反应延迟到达 → 防守决策
            if me.threat_move is not None and frame - me.threat_at >= me.sk['reaction']:
                tm = me.threat_move
                me.threat_move = None
                if me.can_act() and dist <= eff_range(opp) + 16 and me.state != S_DODGE:
                    r = rng.random()
                    if r < me.sk['block_rate'] * 0.55:          # 其中一部分瞄准弹反窗口
                        if me.state != S_BLOCK:
                            me.state = S_BLOCK
                            me.blockf = 0
                            me.parry_until = frame + me.parry_win(momentum)
                        me.block_until = frame + tm['total']
                    elif r < me.sk['block_rate'] * 0.55 + me.sk['dodge_rate']:
                        if me.can_act():
                            me.state = S_DODGE
                            me.dodgef = 0
                            st['dodge_used'] += 1
                            if g_3d:
                                # 3D：闪避方向是"以攻击者为圆心的一个方位角"（09 §3.4 / §4 问题 3）
                                #   dodgeDirs = n → 在 n 个等分方位角里挑一个
                                #     n = 2 → 远离 / 冲向，正是 2D 的"前后二选一"
                                #     n = 0/None → 任意角度（连续）
                                base = math.atan2(me.z - opp.z, me.x - opp.x)
                                if not g_dodge_dirs:
                                    me.dodge_yaw = base + (rng.random() * 2.0 - 1.0) * math.pi
                                else:
                                    k = rng.randrange(int(g_dodge_dirs))
                                    me.dodge_yaw = base + (2.0 * math.pi / g_dodge_dirs) * k
                            else:
                                # 被远程压制时向前闪避穿越距离带，否则向后拉开
                                me.dodge_dir = dirto if dist > my_range * 1.25 else -dirto
                    elif r < me.sk['block_rate'] * 0.55 + me.sk['dodge_rate'] + me.sk['trade_rate']:
                        if me.moves['l1']['startup'] < tm['startup']:
                            start_move(me, 'l1', frame)
                    else:
                        if me.state != S_BLOCK:
                            me.state = S_BLOCK
                            me.blockf = 0
                            me.parry_until = frame + me.parry_win(momentum)
                        me.block_until = frame + tm['total']

            # --- 惩罚对手收招：这是「有利帧」设计的核心兑现 ---
            # 必要条件：自身起手必须能塞进对手剩余的收招帧内，否则惩罚不成反被惩罚。
            # 这解释了为什么重锋（起手 10f）无法惩罚轻击（收招 9f），而影梭（3f）可以。
            opp_rec_left = (opp.move['total'] - opp.mf) if opp_recover else -1
            margin = opp_rec_left - me.moves['l1']['startup'] if opp_recover else -99
            # 有利帧余量越大越好惩罚：惩罚重击收招容易，惩罚轻击收招需要极高的帧精度
            p_punish = me.sk['punish_rate'] * (0.30 + min(1.0, max(0.0, margin / 10.0)))
            if (opp_recover and dist <= my_range and opp_rec_left >= me.moves['l1']['startup']
                    and me.state in (S_IDLE, S_BLOCK)
                    and rng.random() < p_punish):
                start_move(me, 'l1', frame)
                continue

            # 常规节拍（节拍与自身招式长度挂钩：出手越快，攻击机会越多）
            if me.thinkcd > 0:
                me.thinkcd -= 1
                continue
            me.thinkcd = max(3, int(me.moves['l1']['total'] * me.sk['tempo']))

            if me.state in (S_ATTACK, S_DODGE):
                continue

            # ---- 武学技能的使用决策（与原型 aiSkillKind 同源）----
            for skey in ('s1', 's2'):
                sm = me.moves.get(skey)
                if not sm or me.cd.get(skey, 0) > 0:
                    continue
                kind = skill_kind(sm)
                use = 0.0
                if kind == 'defensive':
                    use = 0.40 * me.sk['skill_rate'] if (me.threat_move and dist <= eff_range(opp) + 40) else 0.0
                elif kind == 'offensive':
                    use = 0.55 * me.sk['skill_rate'] if dist <= my_range * 1.2 else 0.0
                elif kind == 'control':
                    use = 0.45 * me.sk['skill_rate'] if dist <= my_range * 1.6 else 0.0
                else:                                   # mobility
                    use = 0.50 * me.sk['skill_rate'] if (dist > my_range * 1.5 or me.cornered(momentum)) else 0.0
                if use > 0 and rng.random() < use:
                    if start_move(me, skey, frame):
                        st['skills'] += 1
                        break

            if me.state == S_ATTACK:
                continue

            if dist <= my_range:
                me.movedir = 0
                # 重整中不进攻（韧性见底时强行开打＝送破防）
                if me.poise < me.sk['regroup_poise']:
                    continue
                r = rng.random()
                # 对手起手越快 → 反应越无效 → 越依赖预判型格挡（3f→1.0, 12f→0.0）
                fastness = max(0.0, min(1.0, 1.0 - (opp.moves['l1']['startup'] - 3) / 9.0))

                # 对手龟缩格挡 → 用重击架崩（兑现"重击 > 格挡"这一环）
                if opp.state == S_BLOCK and r < me.sk['crush_rate']:
                    start_move(me, 'heavy', frame)
                    continue

                if r < me.sk['aggression']:
                    if me.dominant(momentum):
                        start_move(me, 'ult', frame)
                        st['ults'] += 1
                    else:
                        r2 = rng.random()
                        if r2 < 0.50:
                            start_move(me, 'l1', frame)
                        elif r2 < 0.72 and me.sk['combo_rate'] > 0.45:
                            start_move(me, 'l2', frame)
                        elif r2 < 0.86:
                            start_move(me, 'launch', frame)
                        else:
                            start_move(me, 'heavy', frame)
                elif r < me.sk['aggression'] + 0.10 + me.sk['predict_rate'] * fastness:
                    # 预判型防守：对手起手越快，越无法靠反应防住，只能提前架好格挡
                    if me.state != S_BLOCK:
                        me.state = S_BLOCK
                        me.blockf = 0
                        me.parry_until = frame + me.parry_win(momentum)
                    me.block_until = frame + 30

        # ---------- 状态推进 ----------
        for me in seq:
            # 技能冷却
            for ck in me.cd:
                if me.cd[ck] > 0:
                    me.cd[ck] -= 1

            # 韧性回复
            regen = 0.0 if getattr(me, 'attr_suppress', False) else (
            POISE_REGEN_CORNERED if me.cornered(momentum) else POISE_REGEN)
            if me.state != S_BLOCK:
                me.poise = min(MAX_POISE, me.poise + regen)

            me.armored = False
            me.stance = None          # 架势窗口每帧重建，帧内有效

            if me.state == S_BREAK:
                me.stun -= 1
                if me.stun <= 0:
                    me.state = S_IDLE
                    me.poise = MAX_POISE * 0.35
                    me.invuln_until = frame + 20
                continue

            if me.stun > 0:
                me.stun -= 1
                if me.stun <= 0:
                    me.state = S_IDLE
                continue

            if me.state == S_DODGE:
                me.dodgef += 1
                iv0, iv1 = 5, 5 + me.h['invulnFrames'] - 1
                if iv0 <= me.dodgef <= iv1:
                    step = 160.0 / me.h['invulnFrames']      # 总位移量 160px，与 2D 完全一致
                    if g_3d:
                        me.x += step * math.cos(me.dodge_yaw)
                        me.z += step * math.sin(me.dodge_yaw)
                    else:
                        me.x += step * me.dodge_dir
                if me.dodgef >= 20:
                    me.state = S_IDLE
                continue

            if me.state == S_ATTACK:
                me.mf += 1
                m = me.move
                if me.mf == m['startup']:
                    # 前冲位移：量不变，方向由"一维符号"换成"朝向向量"
                    if g_3d:
                        me.x += m.get('lunge', 0) * math.cos(me.yaw)
                        me.z += m.get('lunge', 0) * math.sin(me.yaw)
                    else:
                        me.x += m.get('lunge', 0) * me.facing
                # ---- 判定窗口开启：空挥统计分母 + 绕背姿态采样（几何层统计）----
                if me.mf == m['startup'] + 1:
                    me._atk_open = True
                    me._atk_contact = False
                    me._atk_dodged = False
                    opp0 = B if me is A else A
                    me._atk_rear = bool(g_3d and g_backref == 'rear'
                                        and rear_angle(me, opp0) > g_backang)
                    d0 = geo_dist(me, opp0) if g_3d else abs(opp0.x - me.x)
                    if d0 < CLOSE_R:
                        st['close_atk_inst'] += 1
                if m['armor'] or (me.h['armorFrom'] and m['tier'] == 'heavy'
                                  and me.mf >= me.h['armorFrom']):
                    me.armored = True

                # ---- 武学技能特殊处理 ----
                # 位移：踏雪前突 / 影步瞬移 / 横驱后跳
                if m.get('dashTo') and m['startup'] < me.mf <= m['startup'] + max(1, m['active']):
                    dv = m['dashTo'] / max(1, m['active'])
                    if g_3d:
                        me.x += dv * math.cos(me.yaw)
                        me.z += dv * math.sin(me.yaw)
                    else:
                        me.x += dv * me.facing
                # 无敌窗口（改用招式内帧号判断：invuln 是"相对招式帧"的窗口）
                ivw = m.get('invuln')
                if ivw and ivw[0] <= me.mf <= ivw[1]:
                    me.invuln_until = frame + 1
                # v1.4 强制近身：技能进入收招时开启"无视击退"窗口
                if SIDE_RULES and m.get('no_kb') and me.mf == m['startup'] + max(1, m['active']):
                    me.no_kb_until = frame + m['no_kb']
                # 架势窗口：反击（回风）/ 霸体（镇岳）
                if (m.get('counter') or m.get('armorStance')) \
                        and m['startup'] < me.mf <= m['startup'] + m['active']:
                    me.stance = m
                    if m.get('armorStance'):
                        me.armored = True
                # 部署场域（枪阵）
                if m.get('zone') and me.mf == m['startup'] + 1:
                    z = m['zone']
                    if g_3d:
                        zones.append(dict(x=me.x + z['dist'] * math.cos(me.yaw),
                                          z=me.z + z['dist'] * math.sin(me.yaw),
                                          cfg=z, until=frame + z['duration'], owner=me, tick=0))
                    else:
                        zones.append(dict(x=me.x + z['dist'] * me.facing, cfg=z,
                                          until=frame + z['duration'], owner=me, tick=0))
                # 落地冲击（横驱）
                lz = m.get('landing')
                if lz and me.mf == lz['frame']:
                    opp2 = B if me is A else A
                    if (geo_dist(me, opp2) if g_3d else abs(opp2.x - me.x)) <= lz['radius'] \
                            and opp2.state != S_BREAK:
                        blk2 = opp2.state == S_BLOCK
                        dd = lz['dmg'] * (1.0 - BLOCK_REDUCE) if blk2 else lz['dmg']
                        opp2.hp = max(0.0, opp2.hp - dd)
                        if not blk2:
                            opp2.state = S_HITSTUN
                            opp2.stun = 16
                            if g_3d:
                                opp2.x += lz['knockback'] * math.cos(me.yaw)
                                opp2.z += lz['knockback'] * math.sin(me.yaw)
                            else:
                                opp2.x += lz['knockback'] * me.facing
                        momentum += 5.0 if me.is_p else -5.0
                        if me.is_p:
                            st['a_dmg'] += dd
                        else:
                            st['b_dmg'] += dd
                # 连段取消
                if (me.hitseg > 0 and m['cancel'] > 0
                        and me.mf >= m['startup'] + m['active'] and m['next']
                        and me.buf_move == 'light' and frame - me.buf_at <= 8):
                    nxt = m['next']
                    me.buf_move = None
                    start_move(me, nxt, frame)
                    continue
                if me.mf >= m['total']:
                    finish_atk(me)
                    me.state = S_IDLE
                    me.move = None
                continue

            if me.state == S_BLOCK:
                me.blockf += 1
                if not me.cornered(momentum):
                    me.poise -= BLOCK_DRAIN    # 困兽之斗：格挡不再消耗韧性
                if me.poise <= 0 or me.blockf >= BLOCK_MAX_FRAMES:
                    me.state = S_BREAK
                    me.stun = BREAK_FRAMES
                    me.move = None
                    st['breaks'] += 1
                    continue
                if frame > me.block_until:
                    me.state = S_IDLE
                    me.blockf = 0
                continue

            me.state = S_IDLE

        # ---------- 位移 ----------
        for me in seq:
            opp = B if me is A else A
            if (me.movedir or me.orbit) and me.state in (S_IDLE, S_BLOCK):
                _, spd, _ = me.mods(momentum)
                spd_mult = 0.45 if me.state == S_BLOCK else 1.0   # 格挡推进更慢
                # 枪阵减速
                for z in zones:
                    zi = math.hypot(me.x - z['x'], me.z - z['z']) if g_3d else abs(me.x - z['x'])
                    if z['owner'] is not me and zi <= z['cfg']['radius']:
                        spd_mult *= (1.0 - z['cfg']['slow'])
                speed = me.h['run'] * 0.72 * spd * spd_mult / FPS
                if g_3d:
                    # 移动分解为径向（趋近 / 守距）+ 切向（绕圈）。
                    # 两个分量正交，再做模长归一 → 合速度模长与 2D 版**逐位相同**
                    # （否则"3D 下 AI 变慢/变快"会污染所有胜率对比）
                    dx = opp.x - me.x
                    dz = opp.z - me.z
                    d = math.hypot(dx, dz)
                    if d < 1e-6:
                        ux, uz = 1.0, 0.0
                    else:
                        ux, uz = dx / d, dz / d
                    rx, ry = me.movedir, me.orbit
                    # ★ 关键换算：1D 的 movedir 是"沿世界 x 轴的符号"（+1 = 往 +x 走），
                    #   3D 的径向分量是"朝对手为正"。B 方永远在对手右侧，两者符号相反，
                    #   所以必须先乘一个 dirto 才等价——否则 B 方的"趋近"会变成"后撤"。
                    #   （第一版漏了这一步，导致 B 方行为整体反转、矩阵胜率虚高 8.8pp，
                    #     由镜像对局自检抓出，见 _geo_sweep_result.md 的"被推翻的假设"。）
                    if rx:
                        rx = rx if opp.x > me.x else -rx
                    mag = math.hypot(rx, ry)
                    if mag > 0.0:
                        me.x += speed * (rx * ux + ry * (-uz)) / mag
                        me.z += speed * (rx * uz + ry * ux) / mag
                else:
                    me.x += me.movedir * speed
            me.x = max(90.0, min(1190.0, me.x))
            if g_3d:
                me.z = max(g_zmin, min(g_zmax, me.z))
        if g_3d:
            dx = B.x - A.x
            dz = B.z - A.z
            d = math.hypot(dx, dz)
            if d < 56.0:
                if d < 1e-6:
                    ux, uz = 1.0, 0.0
                else:
                    ux, uz = dx / d, dz / d
                mx = (A.x + B.x) * 0.5
                mz = (A.z + B.z) * 0.5
                A.x = mx - 28.0 * ux
                A.z = mz - 28.0 * uz
                B.x = mx + 28.0 * ux
                B.z = mz + 28.0 * uz
                A.x = max(90.0, min(1190.0, A.x)); A.z = max(g_zmin, min(g_zmax, A.z))
                B.x = max(90.0, min(1190.0, B.x)); B.z = max(g_zmin, min(g_zmax, B.z))
        elif abs(A.x - B.x) < 56:
            mid = (A.x + B.x) / 2.0
            s = 1 if A.x <= B.x else -1
            A.x = mid - 28 * s
            B.x = mid + 28 * s

        # ---------- 朝向更新 ----------
        if g_3d:
            # 09 §3.5「出招即承诺朝向」：2D 的 facing 每帧瞬时对准对手（等价于转向速率 ∞），
            # 3D 必须给出上限，否则朝向永远正确、绕背在数学上不可能发生。
            for me, opp in seq2:
                want = math.atan2(opp.z - me.z, opp.x - me.x)
                if me.state == S_ATTACK:
                    rate = g_turn_atk
                elif me.state in (S_HITSTUN, S_BREAK):
                    rate = 0.0            # 硬直 / 破防：完全不能转向
                elif me.state == S_DODGE:
                    rate = g_turn_dodge
                else:
                    rate = g_turn_idle
                me.yaw = turn_toward(me.yaw, want, rate)
            A.facing = 1 if math.cos(A.yaw) >= 0.0 else -1
            B.facing = 1 if math.cos(B.yaw) >= 0.0 else -1
        else:
            A.facing = 1 if A.x <= B.x else -1
            B.facing = 1 if B.x <= A.x else -1

        # ---------- 距离博弈统计（贴身圈占比）----------
        st['frames'] += 1
        if (geo_dist(A, B) if g_3d else abs(A.x - B.x)) < CLOSE_R:
            st['close_frames'] += 1

        # ---------- 命中结算 ----------
        # 关键：先收集双方命中，再统一结算。
        # 若按固定顺序"边判边结算"，先结算的一方会在同帧交换中白赢，
        # 导致矩阵不对称（A/B 视角胜率之和不等于 100%）。
        pending = []
        for att, dfn in seq2:
            if att.state != S_ATTACK or not att.move:
                continue
            m = att.move
            if not (m['startup'] < att.mf <= m['startup'] + m['active']):
                continue
            if att.hitseg > 0:
                multi = m['hits'] > 1
                if not (multi and att.hitseg < m['hits']
                        and att.mf >= att.lasthit + m['hitInterval']):
                    continue
            if g_3d:
                # ---- 3D 判定：平面距离 ≤ 判定距离  **且**  |朝向夹角| ≤ 扇形半角 ----
                ddx = dfn.x - att.x
                ddz = dfn.z - att.z
                dd = math.hypot(ddx, ddz)
                if dd > eff_range(att) * m.get('rangeMult', 1.0):
                    continue                          # 距离不满足 → 空挥
                ad = ang_diff(math.atan2(ddz, ddx), att.yaw)
                if ad > g_half:
                    continue                          # 角度不满足 → 空挥
                rear = bool(g_backref == 'rear' and rear_angle(att, dfn) > g_backang)
                if g_backref == 'arc' and ad > g_backang:
                    # 任务书字面版：绕背 = 攻击扇形自身的 |Δ角| > 120°。
                    # halfArc ≤ 90° 时上面几行已保证 ad ≤ 90° < 120°，所以这里恒不触发。
                    st['arc_backstab'] = st.get('arc_backstab', 0) + 1
            else:
                if abs(dfn.x - att.x) > eff_range(att) * m.get('rangeMult', 1.0):
                    continue
                dd = abs(dfn.x - att.x)
                ad = 0.0
                rear = False

            # 几何上"可命中"（空挥率的分母/分子口径：判定窗口内是否出现过可命中目标）
            att._atk_contact = True
            st['ang_sum'] += ad

            # 无敌帧
            inv = ((dfn.state == S_DODGE and 5 <= dfn.dodgef <= 5 + dfn.h['invulnFrames'] - 1)
                   or frame < dfn.invuln_until)
            if inv:
                momentum += -4.0 if att.is_p else 4.0
                st['dodges'] += 1
                att._atk_dodged = True
                att.hitseg = m['hits']
                continue

            # ---- 实际结算的命中（含被格挡 / 被弹反）----
            st['contacts'] += 1
            if g_half > 0.0 and (ad / g_half) > g_edge:
                st['edge_hits'] += 1
            if rear:
                st['rear_contacts'] += 1
            if dd < CLOSE_R:
                st['close_contacts'] += 1
            if not st['first_att']:
                st['first_att'] = 'A' if att.is_p else 'B'
                st['first_dist'] = dd
                st['first_close'] = 1 if dd < CLOSE_R else 0

            blocked = dfn.state == S_BLOCK and frame > dfn.parry_until
            parried = dfn.state == S_BLOCK and frame <= dfn.parry_until
            pending.append((att, dfn, m, blocked, parried, ad, rear))

        for att, dfn, m, blocked, parried, ad, rear in pending:
            att.hitseg += 1
            att.lasthit = att.mf
            receive_hit(att, dfn, m, blocked, parried, frame, ad, rear)

        # ---------- 场域结算（长策「枪阵」）----------
        for i in range(len(zones) - 1, -1, -1):
            z = zones[i]
            if frame > z['until']:
                zones.pop(i)
                continue
            tgt = B if z['owner'] is A else A
            zr = z['cfg']['radius']
            zin = (math.hypot(tgt.x - z['x'], tgt.z - z['z']) <= zr) if g_3d \
                else (abs(tgt.x - z['x']) <= zr)
            if zin and tgt.state != S_BREAK:
                z['tick'] += 1
                if z['tick'] % 60 == 0:
                    dd = float(z['cfg']['dps'])
                    tgt.hp = max(0.0, tgt.hp - dd)
                    if z['owner'].is_p:
                        st['a_dmg'] += dd
                    else:
                        st['b_dmg'] += dd

        # ---------- 杀势衰减与钳制 ----------
        if frame - last_combat > MOMENTUM_DECAY_DELAY:
            if momentum > 0:
                momentum = max(0.0, momentum - MOMENTUM_DECAY)
            elif momentum < 0:
                momentum = min(0.0, momentum + MOMENTUM_DECAY)
        momentum = max(-100.0, min(100.0, momentum))

        if A.hp <= 0 or B.hp <= 0:
            break
        # ---- 调试用逐帧轨迹（GEO['trace'] 传入 list 时记录；默认关闭，不影响任何结果）----
        tr = GEO.get('trace')
        if tr is not None and len(tr) < 100000:
            tr.append((frame, round(A.x, 3), round(A.z, 3), round(A.yaw, 4), round(A.hp, 2),
                       round(A.poise, 2), A.state, A.mf, round(momentum, 2),
                       round(B.x, 3), round(B.z, 3), round(B.yaw, 4), round(B.hp, 2),
                       round(B.poise, 2), B.state, B.mf))

    finish_atk(A)
    finish_atk(B)
    if A.hp <= 0 and B.hp <= 0:
        return 'draw', frame, st, momentum
    if B.hp <= 0:
        return 'A', frame, st, momentum
    if A.hp <= 0:
        return 'B', frame, st, momentum
    return 'draw', frame, st, momentum


def win_rate(a_key, b_key, a_sk, b_sk, n, rng, momentum0=0.0):
    wins = 0
    frames = 0
    agg = dict(hits=0, blocks=0, dodges=0, parries=0, breaks=0, execs=0,
               ults=0, counters=0, skills=0)
    for _ in range(n):
        w, f, st, _m = simulate(a_key, b_key, a_sk, b_sk, rng, momentum0)
        if w == 'A':
            wins += 1
        frames += f
        for k in agg:
            agg[k] += st[k]
    return wins / float(n), frames / float(n), agg


# =============================================================================
# 七、四项验证
# =============================================================================
def verify_matrix(n, rng, verbose=True):
    """P2 反制矩阵 + P1 平均胜率"""
    keys = list(HEROES.keys())
    normal = SKILL_LEVELS['normal']
    matrix = {}
    for a in keys:
        for b in keys:
            if a == b:
                continue
            wr, fr, _ = win_rate(a, b, normal, normal, n, rng)
            matrix[(a, b)] = (wr, fr)
            if verbose:
                print('  %-4s vs %-4s  %5.1f%%   平均 %.1fs'
                      % (HEROES[a]['name'], HEROES[b]['name'], wr * 100, fr / 60.0))
    avg = {}
    for a in keys:
        vs = [matrix[(a, b)][0] for b in keys if b != a]
        avg[a] = sum(vs) / len(vs)
    return matrix, avg


def verify_ttk(n, rng, verbose=True):
    """P3 各水平段 TTK"""
    res = {}
    keys = list(HEROES.keys())
    for lvl, sk in SKILL_LEVELS.items():
        tot_f = 0
        tot_n = 0
        agg = dict(hits=0, blocks=0, dodges=0, parries=0, breaks=0, execs=0)
        for i, a in enumerate(keys):
            b = keys[(i + 1) % 4]
            _wr, fr, ag = win_rate(a, b, sk, sk, n, rng)
            tot_f += fr * n
            tot_n += n
            for k in agg:
                agg[k] += ag[k]
        res[lvl] = (tot_f / tot_n, agg, tot_n)
        if verbose:
            avg_f = tot_f / tot_n
            print('  %-6s TTK = %5.1fs' % (sk['label'], avg_f / 60.0))
    return res


def verify_cornered(n, rng, verbose=True):
    """P4 困兽之斗：落后 60 杀势时的翻盘率（同水平对局）"""
    keys = list(HEROES.keys())
    normal = SKILL_LEVELS['normal']
    tot = 0.0
    for i, a in enumerate(keys):
        b = keys[(i + 1) % 4]
        wr, _f, _ = win_rate(a, b, normal, normal, n, rng, momentum0=-60.0)
        tot += wr
        if verbose:
            print('  %-4s 落后60杀势 vs %-4s  胜率 %5.1f%%'
                  % (HEROES[a]['name'], HEROES[b]['name'], wr * 100))
    return tot / len(keys)


def verify_skill_covers_counter(n, rng, verbose=True):
    """P5 技术提升 10% 能否覆盖克制优势"""
    normal = SKILL_LEVELS['normal']
    better = shift_skill(normal, 0.10)
    pairs = [('zhirui', 'zhongfeng'), ('zhongfeng', 'yingsuo'), ('yingsuo', 'changce')]
    out = []
    for a, b in pairs:
        base_wr, _f, _ = win_rate(a, b, normal, normal, n, rng)
        # 劣势方技术提升 10%
        if base_wr >= 0.5:
            fix_wr, _f, _ = win_rate(a, b, normal, better, n, rng)   # B 提升
            improved = 1.0 - fix_wr
        else:
            fix_wr, _f, _ = win_rate(a, b, better, normal, n, rng)   # A 提升
            improved = fix_wr
        out.append((a, b, base_wr, improved))
        if verbose:
            print('  %-4s vs %-4s  原始 %5.1f%%  →  劣势方技术+10%% 后 %5.1f%%'
                  % (HEROES[a]['name'], HEROES[b]['name'], base_wr * 100, improved * 100))
    return out


# =============================================================================
# 八、主流程
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description='《止戈》战斗平衡仿真')
    ap.add_argument('--quick', action='store_true', help='快速抽查（每格 400 局）')
    ap.add_argument('--full', action='store_true', help='高精度（每格 8000 局）')
    ap.add_argument('--n', type=int, default=None, help='每格对局数')
    ap.add_argument('--seed', type=int, default=20260930)
    ap.add_argument('--out', type=str, default='sim_result.json')
    args = ap.parse_args()

    n = args.n if args.n else (400 if args.quick else (8000 if args.full else 2000))
    rng = random.Random(args.seed)
    t0 = time.time()

    print('=' * 74)
    print('《止戈》战斗平衡仿真   每格 %d 局   随机种子 %d' % (n, args.seed))
    print('=' * 74)

    print('\n[P2] 反制矩阵（目标：全部落在 42%% ~ 58%%）')
    matrix, avg = verify_matrix(n, rng)

    print('\n[P1] 各职业平均胜率（目标：48%% ~ 52%%）')
    for k, v in avg.items():
        flag = 'OK ' if 0.48 <= v <= 0.52 else '!! '
        print('  %s%-4s  %5.1f%%' % (flag, HEROES[k]['name'], v * 100))

    print('\n[P3] 各水平段 TTK（目标：新手<=15s / 中 16~22s / 高<=35s）')
    ttk = verify_ttk(n, rng)

    print('\n[P4] 困兽之斗：落后 60 杀势的翻盘率（目标：35%% ~ 42%%）')
    cornered = verify_cornered(n, rng)
    print('  → 平均翻盘率 %5.1f%%' % (cornered * 100))

    print('\n[P5] 技术变量 vs 克制优势（目标：技术+10%% 能覆盖克制）')
    sk = verify_skill_covers_counter(n, rng)

    # ---- 判定 ----
    def ok_p2():
        return all(0.42 <= v[0] <= 0.58 for v in matrix.values())

    def ok_p1():
        return all(0.48 <= v <= 0.52 for v in avg.values())

    def ok_p4():
        return 0.35 <= cornered <= 0.42

    print('\n' + '=' * 74)
    print('验证结论')
    print('=' * 74)
    print('  P1 四职业平均胜率 48%%~52%%      : %s' % ('通过' if ok_p1() else '未通过'))
    print('  P2 反制矩阵 42%%~58%%            : %s' % ('通过' if ok_p2() else '未通过'))
    print('  P3 各水平 TTK 落在目标区间       : 见上表')
    print('  P4 落后翻盘率 35%%~42%%          : %s (%.1f%%)'
          % ('通过' if ok_p4() else '未通过', cornered * 100))
    print('  P5 技术变量覆盖克制优势          : 见上表')

    # 抽样误差提示：小样本下个别对位会因噪声滑出区间，这不是设计问题
    se = (0.25 / n) ** 0.5 * 100
    if n < 800:
        print('')
        print('  ⚠️ 本次每格仅 %d 局，单格标准误约 ±%.1f pp（95%%置信区间 ±%.1f pp）。' % (n, se, se * 1.96))
        print('     小样本下个别对位可能因抽样噪声滑出 42%%~58%%，这不代表设计不达标。')
        print('     定稿结论请用：python combat_balance_sim.py --n 1500 --seed 20260930')
    else:
        print('')
        print('  （每格 %d 局，单格标准误约 ±%.1f pp）' % (n, se))

    print('\n总耗时 %.1f 秒' % (time.time() - t0))

    # ---- 落盘 ----
    out = dict(
        meta=dict(n_per_cell=n, seed=args.seed, heroes={k: v['name'] for k, v in HEROES.items()}),
        matrix={'%s>%s' % (a, b): dict(win_rate=round(v[0], 4), avg_frames=int(v[1]))
                for (a, b), v in matrix.items()},
        avg_win_rate={k: round(v, 4) for k, v in avg.items()},
        ttk={k: dict(seconds=round(v[0] / 60.0, 2), n=v[2], raw=v[1]) for k, v in ttk.items()},
        cornered_win_rate=round(cornered, 4),
        cornered_detail=None,
        skill_covers=[dict(a=a, b=b, base=round(x, 4), after=round(y, 4)) for a, b, x, y in sk],
    )
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('结果已写入 %s' % args.out)


# =============================================================================
# 九、几何维度扫描（本节起为本文件新增内容；上方所有数值与规则一字未改）
# =============================================================================
# 三个必须回答的问题（09 文档 §4）+ 两项补充验证：
#   s1      扇形半角 30/45/60/75/90 → 胜率 / TTK / 空挥率 / 绕背命中占比
#   s2      绕背加成 1.00/1.15/1.25（halfArc=60）→ 是否挤压"抢帧"主轴
#   s3      角度衰减 0/0.35/0.60 → 命中从布尔量变连续量的后果
#   dodge   闪避可选方位角数量 2/4/8/任意 → 与空挥率的关系（§4 问题 3）
#   turn    转向速率上限 → 绕背在数学上是否可能（§4 问题 2 的前置条件）
#   arc_ref 任务书字面版绕背条件（|Δ角|>120°）是否为空操作（证伪用）
#   base    2D 一维基准（原版路径）对照
SCAN_ID = {'base': 1, 's1': 2, 's2': 3, 's3': 4, 'dodge': 5, 'turn': 6, 'arc_ref': 7, 'close': 8}

GEO_BASE_3D = dict(halfArc=60.0, angleFalloff=0.35, backstabMul=1.00, backstabRef='rear',
                   turnIdle=0.10, turnAttack=0.03, turnDodge=0.0, dodgeDirs=2,
                   orbitRate=dict(novice=0.15, normal=0.30, expert=0.50),
                   orbitSmart=dict(novice=0.00, normal=0.50, expert=0.90))


def set_geo(mode='3d', halfArc=60.0, angleFalloff=0.35, backstabMul=1.00, backstabRef='rear',
            turnIdle=0.10, turnAttack=0.03, turnDodge=0.0, dodgeDirs=2,
            orbitRate=None, orbitSmart=None, edgeRatio=None):
    """按"人读的单位"配置几何模式（halfArc 用度），返回当前配置快照"""
    GEO['mode'] = mode
    GEO['halfArc'] = math.radians(halfArc)
    GEO['angleFalloff'] = angleFalloff
    GEO['backstabMul'] = backstabMul
    GEO['backstabRef'] = backstabRef
    GEO['turnIdle'] = turnIdle
    GEO['turnAttack'] = turnAttack
    GEO['turnDodge'] = turnDodge
    GEO['dodgeDirs'] = dodgeDirs
    if orbitRate is not None:
        GEO['orbitRate'] = dict(orbitRate)
    if orbitSmart is not None:
        GEO['orbitSmart'] = dict(orbitSmart)
    if edgeRatio is not None:
        GEO['edgeRatio'] = edgeRatio
    return dict(mode=mode, halfArc_deg=halfArc, angleFalloff=angleFalloff,
                backstabMul=backstabMul, backstabRef=backstabRef,
                turnIdle=turnIdle, turnAttack=turnAttack, turnDodge=turnDodge,
                dodgeDirs=dodgeDirs)


def measure_matrix(n, rng, lvl='normal', start_gap=None):
    """跑完整反制矩阵（4×3 对位 × n 局），返回胜率 / TTK / 几何指标

    口径与 combat_balance_sim.verify_matrix 一致：
      单格胜率 = A 方获胜局数 / n（平局计入分母），与现有报告可比。
      另附 win_rate_dec = 剔除平局后的胜率，用于识别"打不完→平局"造成的失真。
    start_gap：强制双方以指定间距开场（用于"贴身开局"对照实验；None = 默认 440/840）
    """
    sk = SKILL_LEVELS[lvl]
    keys = list(HEROES.keys())
    per, tot = {}, {}
    first = dict(close_n=0, close_win=0, far_n=0, far_win=0)
    games = draws = decided = 0
    fr_all = fr_dec = 0
    for a in keys:
        for b in keys:
            if a == b:
                continue
            wins = 0
            dec = 0
            cellf = 0
            S = {}
            for _ in range(n):
                if start_gap is None:
                    w, f, st, _m = simulate(a, b, sk, sk, rng)
                else:
                    w, f, st, _m = simulate(a, b, sk, sk, rng,
                                            a_x=440.0, b_x=440.0 + float(start_gap))
                games += 1
                cellf += f
                fr_all += f
                if w == 'draw':
                    draws += 1
                else:
                    dec += 1
                    decided += 1
                    fr_dec += f
                    if w == 'A':
                        wins += 1
                for k, v in st.items():
                    tv = type(v)
                    if tv is int or tv is float:
                        S[k] = S.get(k, 0) + v
                fa = st['first_att']
                if fa:
                    if st['first_close']:
                        first['close_n'] += 1
                        first['close_win'] += 1 if w == fa else 0
                    else:
                        first['far_n'] += 1
                        first['far_win'] += 1 if w == fa else 0
            per['%s>%s' % (a, b)] = dict(
                win_rate=wins / float(n),
                win_rate_dec=(wins / float(dec)) if dec else None,
                draw_rate=1.0 - dec / float(n),
                ttk_dec_s=(cellf / float(dec) / 60.0) if dec else None,
                ttk_all_s=cellf / float(n) / 60.0)
            for k, v in S.items():
                tot[k] = tot.get(k, 0) + v
    avg = {}
    for a in keys:
        vs = [per['%s>%s' % (a, b)]['win_rate'] for b in keys if b != a]
        vd = [per['%s>%s' % (a, b)]['win_rate_dec'] for b in keys if b != a]
        avg[a] = dict(name=HEROES[a]['name'], win_rate=sum(vs) / len(vs),
                      win_rate_dec=sum(vd) / len(vd))
    A = tot

    def rate(x, y):
        return (A.get(x, 0) / float(A[y])) if A.get(y) else None

    contacts = A.get('contacts', 0)
    metrics = dict(
        atk_inst=A.get('atk_inst', 0), contacts=contacts,
        whiff_rate=rate('whiff_geo', 'atk_inst'),
        whiff_dodge_rate=rate('whiff_dodge', 'atk_inst'),
        contact_rate=rate('contacts', 'atk_inst'),
        edge_rate=(A.get('edge_hits', 0) / float(contacts)) if contacts else None,
        rear_share=(A.get('rear_contacts', 0) / float(contacts)) if contacts else None,
        rear_inst=A.get('rear_inst', 0),
        rear_conv=(A.get('rear_inst_hit', 0) / float(A['rear_inst'])) if A.get('rear_inst') else None,
        backstab_hits=A.get('backstab_hits', 0),
        arc_backstab=A.get('arc_backstab', 0),
        mean_angle_deg=(math.degrees(A.get('ang_sum', 0.0) / contacts)) if contacts else None,
        close_frame_share=(A.get('close_frames', 0) / float(A.get('frames', 1))),
        close_atk_inst=A.get('close_atk_inst', 0),
        close_contact_rate=(A.get('close_contacts', 0) / float(A['close_atk_inst']))
        if A.get('close_atk_inst') else None,
        dodge_used=A.get('dodge_used', 0), dodge_evade=A.get('dodges', 0),
        hits=A.get('hits', 0), blocks=A.get('blocks', 0), parries=A.get('parries', 0),
        breaks=A.get('breaks', 0), execs=A.get('execs', 0), skills=A.get('skills', 0),
    )
    out = dict(
        n_per_cell=n, games=games,
        mean_win_rate=sum(v['win_rate'] for v in avg.values()) / len(avg),
        mean_win_rate_dec=sum(v['win_rate_dec'] for v in avg.values()) / len(avg),
        spread_pp=(max(v['win_rate'] for v in avg.values())
                   - min(v['win_rate'] for v in avg.values())) * 100.0,
        ttk_dec_s=(fr_dec / float(decided) / 60.0) if decided else None,
        ttk_all_s=fr_all / float(games) / 60.0,
        draw_rate=draws / float(games),
        avg_hero=avg, pairs=per, metrics=metrics, agg=tot,
        first=dict(close_n=first['close_n'], far_n=first['far_n'],
                   close_share=first['close_n'] / float(max(1, first['close_n'] + first['far_n'])),
                   close_win_rate=(first['close_win'] / float(first['close_n'])) if first['close_n'] else None,
                   far_win_rate=(first['far_win'] / float(first['far_n'])) if first['far_n'] else None),
    )
    return out


def _cells_for(scan):
    """一个扫描的格子定义：[(label, geo_overrides), ...]"""
    if scan == 'base':
        return [('1D 一维基准（2D 原版路径）', dict(mode='1d'))]
    if scan == 's1':
        return [('halfArc=%d°' % h, dict(halfArc=float(h))) for h in (30, 45, 60, 75, 90)]
    if scan == 's2':
        cells = [('backstabMul=%.2f' % m, dict(backstabMul=m)) for m in (1.00, 1.15, 1.25)]
        # 补充：把转向速率降到 0.02 rad/帧后，绕背在数学上才可能发生（见 turn 扫描），
        # 只有在这种配置下"绕背加成"才是真旋钮——否则上面三格必然完全相同。
        cells += [('绕背可达时 mul=%.2f (turnIdle=0.02)' % m, dict(backstabMul=m, turnIdle=0.02))
                  for m in (1.00, 1.25)]
        return cells
    if scan == 's3':
        return [('angleFalloff=%.2f' % k, dict(angleFalloff=k)) for k in (0.0, 0.35, 0.60)]
    if scan == 'dodge':
        return [('方位角数量=%s' % ('任意(连续)' if d == 0 else d), dict(dodgeDirs=d))
                for d in (2, 4, 8, 0)]
    if scan == 'turn':
        return [('turnIdle=%.2f rad/帧' % t, dict(turnIdle=t)) for t in (0.20, 0.10, 0.05, 0.03, 0.02)]
    if scan == 'arc_ref':
        return [('字面绕背 |Δ角|>120° (mul=1.25)', dict(halfArc=90.0, backstabMul=1.25, backstabRef='arc')),
                ('对照：背后扇区 (mul=1.25)', dict(halfArc=90.0, backstabMul=1.25, backstabRef='rear'))]
    if scan == 'close':
        # 贴身开局对照：强制双方以 56px（分离下限）开场，直接观察"贴身圈内的先手归属"
        return [('1D 贴身开局 56px', dict(mode='1d', start_gap=56.0)),
                ('3D 贴身开局 56px (halfArc=60°)', dict(start_gap=56.0))]
    return []


def run_scan(scan, n, seed, lvl='normal', verbose=True):
    cells_out = []
    for i, (label, ov) in enumerate(_cells_for(scan)):
        cfg = dict(GEO_BASE_3D)
        cfg.update(ov)
        mode = cfg.pop('mode', '3d')
        start_gap = cfg.pop('start_gap', None)
        snap = set_geo(mode=mode, **cfg)
        # 每格独立 RNG：与扫描序号 + 格子序号绑定，跨进程/跨机器可复现
        rng = random.Random(seed if scan == 'base'
                            else seed * 7919 + 1000 * SCAN_ID.get(scan, 99) + i)
        t0 = time.time()
        r = measure_matrix(n, rng, lvl, start_gap=start_gap)
        r['label'] = label
        r['geo'] = snap
        r['start_gap'] = start_gap
        r['seconds'] = round(time.time() - t0, 1)
        m = r['metrics']
        if verbose:
            print('  [%s] %-34s 胜率 %5.1f%%  极差 %4.1fpp  TTK %5.1fs  空挥 %5.1f%%  '
                  '绕背占比 %5.2f%%  平局 %4.1f%%  %.0fs'
                  % (scan, label, r['mean_win_rate'] * 100, r['spread_pp'],
                     r['ttk_dec_s'] or 0.0, (m['whiff_rate'] or 0.0) * 100,
                     (m['rear_share'] or 0.0) * 100, r['draw_rate'] * 100, r['seconds']))
            sys.stdout.flush()
        cells_out.append(r)
    return dict(scan=scan, n=n, seed=seed, level=lvl, cells=cells_out)


def run_parity(n=200, seed=20260930, lvl='normal'):
    """自证：1D 路径与原文件逐位一致；3D 专属参数在 1D 下不产生任何影响"""
    import combat_balance_sim as ORIG
    ok = True
    print('')
    print('=== 几何扩展自证（parity）===')
    # (1) 1D 逐位一致
    set_geo(mode='1d')
    r1 = random.Random(seed)
    r2 = random.Random(seed)
    sk = SKILL_LEVELS[lvl]
    bad = []
    for a in ORIG.HEROES:
        for b in ORIG.HEROES:
            if a == b:
                continue
            w1, f1, _ = ORIG.win_rate(a, b, sk, sk, n, r1)
            w2, f2, _ = GEO1D_win_rate(a, b, sk, sk, n, r2)
            if w1 != w2 or f1 != f2:
                bad.append('%s>%s %s/%s vs %s/%s' % (a, b, w1, f1, w2, f2))
    print('  [1] 1D 逐位一致（%d 对位 × %d 局）：%s'
          % (12, n, '✅ 一致' if not bad else '❌ 不一致 %s' % bad[:3]))
    ok = ok and not bad
    # (2) 3D 专属参数在 1D 模式下属空操作
    set_geo(mode='1d', halfArc=30.0, angleFalloff=0.60, backstabMul=1.25, turnIdle=0.02, dodgeDirs=8)
    r3 = random.Random(seed)
    r4 = random.Random(seed)
    bad2 = []
    for a in ORIG.HEROES:
        for b in ORIG.HEROES:
            if a == b:
                continue
            w1, f1, _ = ORIG.win_rate(a, b, sk, sk, n, r3)
            w2, f2, _ = GEO1D_win_rate(a, b, sk, sk, n, r4)
            if w1 != w2 or f1 != f2:
                bad2.append('%s>%s' % (a, b))
    print('  [2] 3D 参数在 1D 路径上的空操作（改满参数后仍逐位一致）：%s'
          % ('✅ 一致' if not bad2 else '❌ 有影响 %s' % bad2[:3]))
    ok = ok and not bad2
    # (3) 3D 路径同种子可复现
    set_geo(mode='3d')
    a1 = measure_matrix(60, random.Random(seed), lvl)
    a2 = measure_matrix(60, random.Random(seed), lvl)
    same = abs(a1['mean_win_rate'] - a2['mean_win_rate']) < 1e-12 and a1['metrics'] == a2['metrics']
    print('  [3] 3D 路径同种子复现：%s' % ('✅ 完全一致' if same else '❌ 不可复现'))
    ok = ok and same
    print('  → 结论：%s' % ('✅ 扩展只动了空间维度，机制层未受影响' if ok else '❌ 存在越界改动'))
    return ok


def GEO1D_win_rate(a_key, b_key, a_sk, b_sk, n, rng, momentum0=0.0):
    """仅用于 parity 自证的 1D 胜率（与 combat_balance_sim.win_rate 同口径）"""
    wins = 0
    frames = 0
    for _ in range(n):
        w, f, _st, _m = simulate(a_key, b_key, a_sk, b_sk, rng, momentum0)
        if w == 'A':
            wins += 1
        frames += f
    return wins / float(n), frames / float(n), None


def merge_parts(paths, out_path):
    """把多个分片 JSON 合并成一份 sim_geo_sweep.json"""
    merged = dict(meta=None, scans={})
    for p in paths:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        if merged['meta'] is None:
            merged['meta'] = d.get('meta')
        for k, v in d.get('scans', {}).items():
            merged['scans'][k] = v
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print('已合并 %d 个分片 → %s（扫描组：%s）'
          % (len(paths), out_path, ', '.join(sorted(merged['scans']))))
    return merged


def main_geo():
    ap = argparse.ArgumentParser(description='《止戈》3D 几何维度仿真扫描')
    ap.add_argument('--scan', default='all', help='base|s1|s2|s3|dodge|turn|arc_ref|all（逗号分隔）')
    ap.add_argument('--n', type=int, default=500, help='每格（对位）局数')
    ap.add_argument('--seed', type=int, default=20260930)
    ap.add_argument('--level', default='normal', choices=['novice', 'normal', 'expert'])
    ap.add_argument('--out', default=None)
    ap.add_argument('--parity', action='store_true', help='自证 1D 路径与原文件逐位一致')
    ap.add_argument('--merge', nargs='*', default=None, help='合并分片 JSON 到 --out')
    args = ap.parse_args()

    if args.merge is not None:
        merge_parts(args.merge, args.out or 'sim_geo_sweep.json')
        return 0
    if args.parity:
        return 0 if run_parity(min(args.n, 200), args.seed, args.level) else 1

    scans = list(SCAN_ID.keys()) if args.scan == 'all' else [s.strip() for s in args.scan.split(',')]
    t0 = time.time()
    print('=' * 78)
    print('《止戈》3D 几何维度扫描   每格 %d 局   种子 %d   水平 %s' % (args.n, args.seed, args.level))
    print('  只改空间维度：帧数据/伤害/削韧/击退/杀势/韧性/连段/技能参数一字未改')
    print('=' * 78)
    res = dict(meta=dict(
        n_per_cell=args.n, seed=args.seed, level=args.level, scans=scans,
        close_r=CLOSE_R, geo_base=dict(
            halfArc_deg=GEO_BASE_3D['halfArc'], angleFalloff=GEO_BASE_3D['angleFalloff'],
            backstabMul=GEO_BASE_3D['backstabMul'], turnIdle=GEO_BASE_3D['turnIdle'],
            turnAttack=GEO_BASE_3D['turnAttack'], dodgeDirs=GEO_BASE_3D['dodgeDirs']),
        note='mode=1d 的格子 = 2D 一维原版路径（逐位复现 combat_balance_sim.py）',
        heroes={k: v['name'] for k, v in HEROES.items()},
    ), scans={})
    for s in scans:
        if not _cells_for(s):
            print('  !! 未知扫描 %s' % s)
            continue
        print('\n--- 扫描 %s ---' % s)
        res['scans'][s] = run_scan(s, args.n, args.seed, args.level)
    print('\n总耗时 %.1f 秒' % (time.time() - t0))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print('结果已写入 %s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main_geo())
