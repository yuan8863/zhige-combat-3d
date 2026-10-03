# 《止戈》蓄力攻击（蓝霸体）机制研究报告

> 检索日期：本轮会话　|　抽样来源以 NARAKA: BLADEPOINT 社区 Wiki（旧站 old.naraka.wiki）为主，辅以中文攻略站、Ubisoft 官方公告、格斗游戏术语词典。
>
> **可信度分级**（全文沿用）：
> - 🟢 **有来源支撑**：据下列链接原文
> - 🟡 **推断**：我的分析，无直接来源
> - 🔴 **未查到**：找不到可靠来源，**不填数值**

---

## 0. 一句话结论

《永劫无间》的"蓝霸体"本质是**一个带 30% 减伤、能硬吃普攻、但不免疫振刀的蓄力状态**（🟢）。它的强度**不来自霸体本身，而来自三角闭环**——蓝霸体克普攻、振刀克蓝霸体、普攻克振刀。本项目当前把"蓝霸体"这一环做成了**纯增益**（×1.6 伤害 / ×1.8 削韧 / 霸体 / guardCrush），但目前**没有任何东西真正克制它**（振刀是 P0-C 才补），这是最大的风险，比倍率高低重要得多。

---

## 1. 蓝霸体的规则与关键数值

### 1.1 什么是"霸体（Focus）"🟢

来源：[old.naraka.wiki / Focus](https://old.naraka.wiki/en/Focus)

| 项 | 规则（原文要点） |
|---|---|
| 触发 | 按住左键或右键（Hold LMB or RMB） |
| 核心性质 | 「Restrains common attacks and **cannot be interrupted by common attacks**」——**克制普攻、且不被普攻打断**，这就是"霸体"的语义 |
| 克制链 | **Extreme > Ultimate > Parry > Gold > Purple / Blue** |

### 1.2 蓝霸体（Blue Focus）具体规则 🟢

- 角色身上显示**蓝色覆盖材质**——这是可读性信号（蓝光 = 我现在是蓝霸体）
- **可被振刀反制**（"Can be countered"）
- 可与**蓝霸体、紫霸体**对刀（"Can clash with Blue Focus and Purple Focus strikes"）
- **给 30% 减伤**（若该 Focus 状态来自武器；终极武器除外）
  - 减伤在**状态正常结束或被中断时立刻失效**
  - 若被一次攻击打断，**那次攻击不吃这 30% 减伤**
- 紫霸体（Purple）：**不可被振刀**、可被金霸体打断、**蓝霸体打断不了紫霸体（只能对刀）**
- 金霸体（Gold）：不可振刀，只能与金霸体对刀
- 终极（Ultimate）/极限（Extreme）：不可振刀、不可打断；Extreme 减伤约 **50%** 且**无视无敌帧**

### 1.3 霸体覆盖哪一段？🟢（以阔刀/巨剑为样本）

来源：[old.naraka.wiki / Weapons / Greatsword](https://old.naraka.wiki/en/Weapons/Greatsword)

原文对阔刀各招的霸体覆盖写得很细：

- 「Grants **Regular Stone Form during charge state and during the move start-up frames**」（蓄力段 + 起手段）
- 部分招式「Grants **Invincible Stone Form during the move charge state, start-up frames and active frames**」（蓄力段 + 起手 + **判定段**）
- 灵魂玉「Infernal Slash」：「Grants Blue Focus state **during the entire move**」（**全程**）

**结论（🟢）**：**不是统一规则**。基准是"**蓄力段 + 起手段**"；特定招式/玉可以扩到判定段乃至全程。**这正好是本项目可以直接照抄的分层设计**。

### 1.4 蓄力分几档 / 满蓄耗时多久？

- **档位 🟢（间接）**：阔刀的招式表里出现 **Storm Slash (Stage 1 / 2 / 3)**、**Rockfall Slash (Stage 1/2/3)**、**Sky Cutter (Stage 1/2/3)**，并有玉的描述为「Alters moves of the **charged third-stage** horizontal strike」→ **阔刀类重刃至少是三段蓄力**。
- **满蓄耗时 🔴 未查到可靠数值**：该 Wiki 的阔刀招式帧数据表**整张都是 `??`**（起手/判定/收招/总帧全部未填），官方也未公布蓄力秒数。
  - 检索到一条中文视频标题《单排顶尖玩家的蓄力理解丨**1.0 1.2 1.5**？》（[bilibili](https://www.bilibili.com/opus/716554107405467734)），**疑似**指三档蓄力的秒数（1.0s / 1.2s / 1.5s），但我**未能读取正文验证**，**故不能作为数值依据**。

### 1.5 被什么打断？🟢

- **不被普攻打断**（这是它的定义）
- **可被振刀反制**（Parry）→ 这是蓝霸体唯一的硬解
- 紫霸体只有金霸体/终极/极限能打断它
- Parry Focus 状态「**Cannot be interrupted by anything except Ultimate Focus and Extreme Focus attacks**」，且**不可对刀**

### 1.6 顺带查到的高价值参照：振刀起手帧 🟢🟢

来源：[old.naraka.wiki / Combat](https://old.naraka.wiki/en/Combat)
（表中"Time (Frames)"= **振刀判定生效所需时间**）

| 振刀类型 | 起手帧 | 时间 |
|---|---|---|
| 复合振刀 / 快捷振刀 | **15f** | 0.25s |
| 剪式（Scissors）振刀 | **10f** | 0.16s |
| 下蹲 / 跳跃振刀 | **20f** | 0.33s |
| 冲刺中复合振刀 | **7f** | 0.12s |
| 中段闪避复合振刀 | **7f** | 0.12s |

> 注：表中时间随延迟（ping）增加，需自行加上 ping。
> **这组数字对本项目极其重要**：振刀起手 15f（0.25s）说明在《永劫无间》里**振刀是"预判"而不是"反应"**——人类反应约 250ms，单靠看到再振是来不及的。项目现在的"弹反窗口 8 帧"如果做成**瞬时生效的窗口**，实际是比永劫更宽松的设计。

---

## 2. 对刀/拼刀 与 磐石架势

### 2.1 对刀（Clash）规则 🟢

来源：[old.naraka.wiki / Focus](https://old.naraka.wiki/en/Focus)

- 蓝霸体「**Can clash with Blue Focus and Purple Focus strikes**」
- 紫霸体「Can clash with Blue Focus and Purple Focus strikes, **but cannot be interrupted by Blue Focus (only clash)**」
- 金霸体「**Can clash with Gold Focus**」
- 关键补充原文：「If for some reasons (i.e. hero ability or attack angle) the Blue Focus attack **cannot clash** with the Purple Focus attack, the attacker **will not stagger the target**.」

**读法（🟡 推断）**：双方同时进入霸体出招 → **进入对刀判定**，结果是"**不产生硬直**"（互相弹开/相持），而不是单方面吃伤害。且对刀**可能因为攻击角度或英雄技能而失败**——即"同时出招"不是一定对刀，角度差会导致对刀不成立但也不产生硬直。

### 2.2 磐石架势（Stone Form）🟢🟢 —— 这是阔刀专属防御机制

来源：[old.naraka.wiki / Weapons / Greatsword](https://old.naraka.wiki/en/Weapons/Greatsword)

| 项 | 规则 |
|---|---|
| 归属 | **阔刀（巨剑）专属防御机制**，只有特定招式在特定时刻赋予 |
| 触发 | 被攻击时若正处于 Stone Form → **架势激活，受到伤害降低 90%** |
| 反击窗口 | **「After a while (**30 to 72 frames**), if an attack button has been pressed while in Stone Form, a retaliation move is performed」** —— 即 30~72 帧内按攻击键可打出**磐石反击** |
| 可选项 | 「If the player did not hold the attack button immediately after blocking, the retaliation move **can be delayed or chosen not to be performed**」——**可以不反击** |
| 两种形态 | **Regular Stone Form**：格挡 **220° 角度内**的**普攻**；**Invincible Stone Form**：格挡 **220° 角度内**的**蓝霸体攻击** |
| 何时是哪种 | ①连续攻击中"接在上一招之后的攻击"→ 无敌磐石；②**移动中 → 整个蓄力段都是普通磐石**；③部分招式判定帧自带无敌磐石；④**切换移动状态后的第一次攻击 → 蓄力段为普通磐石** |

> **对标价值（🟡）**：磐石架势 = "**防御状态下的反击期权**"。它解决的是"防守方完全被动"的问题：防守不再是纯亏损，而是一个**有 30~72 帧窗口、可选是否兑现**的反打承诺。本项目目前只有"格挡减伤 80%"和"弹反"，**没有"防守成功后带期权的反打"**——这是可以借鉴的第二个机制（若做，建议窗口 20~30 帧，因为项目节拍比永劫快）。

---

## 3. 振刀成功后的处理：兵刃脱手 / 武器掉落

### 3.1 有来源的部分 🟢

来源：[old.naraka.wiki / Focus](https://old.naraka.wiki/en/Focus)

- 振刀成功 → 进入 **Parry Focus** 状态
- 原文：「Acquired when an enemy has been **countered**, but the **parry riposte has not been started yet**」
- Parry Focus「**Will consequently counter any upcoming Blue Focus attacks in a 270 degrees** relative to the player's current heading」，且「**Heading will update after each subsequent parries**」（每次振刀后朝向刷新）
- Parry Focus 本身**不给任何减伤**，但**振刀反击招式（parry riposte）给 70% 减伤**
- Parry Focus「Cannot be interrupted by anything except Ultimate Focus and Extreme Focus attacks」，且**不可对刀**
- 阔刀的振刀反击伤害 = **2.90 × 攻击力**（🟢）

### 3.2 兵刃脱手/武器掉落的时间 🔴 **未查到可靠来源**

- 官方与社区 Wiki **均未给出"武器掉落持续多少帧/秒"**的数值。
- 仅检索到低质量中文攻略站称：振刀会**打掉敌人武器**、玩家可**拾取**对方武器；被振刀者**可以重新捡回**，**无武器期间伤害大幅降低，直到捡回才恢复**。
  - 来源：[九游《永劫无间》振刀作用是什么](https://www.9game.cn/news/5629872.html)（🟡 低质量来源，**无帧数/秒数**）
- 也检索到玩家讨论"处决（处决）与振刀的关系"的内容，但**未找到可引用的规则文本**。
- **结论：这一条我不给数值。** 若必须给参数，只能按下面第 7 节的**推断值**并用探针验证。

---

## 4. 蓄力阈值与"按下即出招 vs 松手出招"

### 4.1 未查到的部分 🔴（诚实交代）

- 《怪物猎人》大剑三段蓄力的**秒表数值**：检索到中文页面《怪物猎人世界三段大剑攻击蓄力伤害详解》([9game](https://www.9game.cn/gwlrsj/2040097.html))，**我未能读取正文**，故**不给数值**。
- 《黑暗之魂》《只狼》《街霸》的蓄力阈值/charge 帧数：**🔴 未查到可靠一手来源**。
- **"一般推荐的按下→判定延迟是多少毫秒"：🔴 未查到权威数值。** 我能找到的、与该项目直接相关的唯一"来源"是项目自身引用的手感文章：
  - [《论如何做好动作游戏的基础操作手感（下）——技能时间轴 / 取消段 / 辅助转向 / 预输入》](https://www.gameres.com/898209.html) —— 项目据此采用了**预输入窗口 0.2~0.3 秒**（本项目取 12 帧 = 0.2s）。**注意：这是预输入窗口，不是蓄力阈值，不能混用。**

### 4.2 有来源的部分 🟢

- **"松开按键也算一次输入"是格斗游戏里的既有术语 negative edge**，收录于 [The Fighting Game Glossary (infil.net)](https://glossary.infil.net/?t=Negative%20Edge)。这正是"松手出招"方案必须处理的输入学问题（🟢 术语存在；🟡 具体定义我未逐字引用）。
- **按下即出招方案的项目内依据**：原型代码注释已写明「"必须等松手才出招"的方案反馈不即时……按下的第一帧就挥」，并把"按下 → 首个可感知动作"定在 **1~3 帧**（🟡 项目自定，非外部来源）。

### 4.3 两种方案的取舍（🟡 推断，基于以上来源的推论）

| 方案 | 优点 | 代价 | 代表 |
|---|---|---|---|
| **按下即出招**（按下先挥，松手时再决定是否满蓄） | 响应即时（1~3 帧有反馈）；不依赖松手精度；无 negative edge 问题 | 动作"先有了再变强"，**满蓄的神态不清**——玩家看到招式已经挥出，很难立刻意识到"这是可蓄力的"；需要额外的可读性设计 | 本项目当前方案 |
| **松手出招**（按住蓄，松手放） | 蓄力段与判定段的界限清晰，可读性强；"承诺成本"直观 | 按下的前若干帧**没有任何动作反馈**，玩家会以为"输入丢了"；依赖松手精度，引入 negative edge 问题 | 需按第 4.1 节补证 |

---

## 5. 蓄力机制的设计教训 / 失败案例

### 5.1 已定位但**未能读取正文**的权威来源 🟡→🔴

- **Ubisoft 官方**：[For Honor — Public Test: Meta Changes](https://www.ubisoft.com/en-au/game/for-honor/news-updates/1IZoiczWorTTTsrEYprgzR/public-test-meta-changes)
  - 《荣耀战魂》上线初期的著名问题是"**防守型 meta / 龟缩 meta（defensive / turtle meta）**"——防守（格挡/招架）的收益高于进攻，导致对局退化为互相观望。Ubisoft 为此做过公开测试并重做招架/破防奖励。
  - **但该页面正文我未读取**，故**具体改动的数值我不引用**。
- 同期的 For Honor 补丁说明（Steam 公告，appid 304390）已定位，但**同样未读取**。

### 5.2 能从已有来源推出的教训 🟡

1. **"不可打断 + 高收益"必须有明确的唯一解，否则战斗会退化成互相蓄力。**
   《永劫无间》的蓝霸体之所以没有让游戏变成双方对峙，是因为它**有代价地可被振刀反制**（🟢 Focus 页原文 "Can be countered"），而且它的**减伤只有 30%**（🟢），不是无敌。
   → 反推：**如果本项目做出"霸体 + 高倍率 + 无克制手段"，玩家理性选择就是双方都按住不放**，这正是项目注释里担心的"互相蓄力"，而目前**振刀还没补上（代码注释写 P0-C）**，所以风险是**公开存在**的。

2. **霸体覆盖"全程"是危险的，分层覆盖是安全的。**
   永劫里"全程蓝霸体"只出现在特定灵魂玉改造的招式上，**基准招式只覆盖"蓄力段 + 起手段"**（🟢）。这说明连原厂也把"全程霸体"当作**罕见的特权**，而不是基准。

3. **减伤与"能硬吃"不要叠加。**
   永劫的蓝霸体给的是 **30% 减伤**（🟢）；而本项目的霸体给的是**"完全不吃轻击僵直"**（叠加受击）。**这两者是同一件事的两种做法**——一个削伤害，一个免僵直。**同时给会显著超模**（🟡）。

### 5.3 明确未查到 🔴

- **具体的"蓄力过强导致战斗退化"的可引用案例与数值改动**：🔴 未查到（For Honor 那条我只确认了页面存在，未读正文）。
- **"取消路径太多导致没有承诺成本"的具体案例**：🔴 未查到可引用的来源（这条我未完成检索）。

---

## 6. MC 模组的蓄力与体力（Epic Fight / Better Combat）

### 6.1 结论 🔴 **数值未查到**

我**定位到了权威来源，但未能读取到正文数值**，因此**不填任何数字**：

- **Epic Fight**：官方文档站 [epicfight-docs.readthedocs.io](https://epicfight-docs.readthedocs.io/)，其中确有 **Misc / Gameplay** 页与按武器分类的 **Compendium**（如 Diamond Greatsword / Iron Spear / Uchigatana 等）条目页，结构上应当包含每招的伤害与消耗表。
  - 相关线索：[Gameplay - Epic Fight Wiki](https://epicfight-docs.readthedocs.io/ja/Misc/Gameplay/)、[Skills 页](https://epicfight-docs.readthedocs.io/ja/Misc/Gameplay/skills/)（含 Berserker 等技能）
- **Better Combat**：
  - [Modrinth: Better Combat](https://modrinth.com/mod/better-combat)（描述为"来自 Minecraft Dungeons 的近战系统"，**其定位是攻击动作/连段与武器属性，而不是体力层**——🟡 由描述推出的印象，**未逐条核实**）
  - [MC百科：Better Combat](https://www.mcmod.cn/class/7110.html)
  - **可能含数值的最佳线索**：[Better Combat 重生 config 汉化帖](https://www.mcmod.cn/post/2068.html)（配置项汉化通常逐项列出数值默认值）
- **关于"有没有蓄力重击 / 体力层"这个问题本身**：🔴 **我未能核实，因此不作断言。**（检索中确实出现了"蓄力攻击"字样的第三方整合包介绍页，但那不是 Epic Fight / Better Combat 本体，不能作为结论。）

> **给下一轮的建议**：要拿到这两组数值，最短路径是读 Epic Fight 文档站的 **Compendium → 具体武器条目页**（每招的 damage / stamina cost 表），以及 Better Combat Rebirth 的 **config 汉化帖**。这两处都不需要登录。

---

## 7. 对本项目的可执行建议

先对齐现状（我从 `作品集-雷火战斗策划\原型\止戈-战斗原型-3D.html` 的 `CHARGE` 常量与共享数据块读到，🟢 代码事实）：

```
CHARGE = { fullFrames:12, pressWindow:4, armorFrom:4, maxHold:30, dmg:1.6, poise:1.8, swing:'heavy' }
heavy  = 18/5/24, dmg 185, poise 38, tier heavy, guardCrush:true
MAX_HP 1200 | MAX_POISE 100 | POISE_REGEN 12/s | BLOCK_DRAIN 10/s
BLOCK_POISE_MULT 0.5 | HEAVY_VS_BLOCK_POISE_MULT 1.8 | PARRY_POISE_CORNERED 40
REACT_FRAMES 9 | CANCEL.freeTail 4 | CANCEL.inputBuffer 12 | HITSTOP.tierMul.heavy 1.5
```

### 7.1 最高优先级：先补"振刀"，否则不要动倍率 🟡（理由有来源）

**问题**：当前满蓄斩有**霸体 + ×1.6 伤害（296）+ ×1.8 削韧（68.4）+ guardCrush**，而**振刀（唯一克制手段）还没实现**。在这种状态下，玩家理性策略就是**双方都按住不放**——这正是要避免的对峙。
《永劫无间》的蓝霸体之所以健康，靠的是**"可被振刀"这个出口**（🟢 [Focus 页](https://old.naraka.wiki/en/Focus)），而不是靠倍率调得多准。

**建议**：把"满蓄斩必被弹反克制"作为 P0，与蓄力同批上线。并在探针里把 `CHARGESTAT.被弹反` 作为硬指标。

### 7.2 帧数建议表

| 参数 | 现值 | 建议值 | 依据 |
|---|---|---|---|
| `fullFrames` 满蓄阈值 | 12f (0.2s) | **保持 12f** | 🟡 与 `REACT_FRAMES=9` 对齐：12f 略高于反应阈值，使"满蓄成形"这一步对手来不及反应，只能对"放出"反应。若改到 18f（0.3s），对手可以反应过来并预判振刀，蓄力会直接失去使用率 |
| `maxHold` 上限 | 30f (0.5s) | **保持 30f**（可考虑 24f） | 🟡 上限越长，越接近"举刀对峙"。30f 已经够对手做一次反应但不够绕背，作者的理由（避免静态对峙）成立 |
| `armorFrom` 霸体起始 | 第 4f | **保持第 4f**，但**必须改写设计说明** | 🟡 见 7.3，这是本报告最重要的修正 |
| `pressWindow` 未成形窗口 | 前 4f | **保持 4f** | 🟡 同 7.3 |
| `dmg` 伤害倍率 | ×1.6 (296) | **保持 ×1.6** | 🟡 296 = 1200 HP 的 24.7%，3 次满蓄可斩杀；与轻击连段（62+78+115=255）拉开可读差距，惩罚强度足够 |
| `poise` 削韧倍率 | ×1.8 (68.4) | **降到 ×1.3**，并加"单段削韧上限"硬护栏 | 🟡 见 7.4，**这是当前最明确的一个超模点** |
| guardCrush × 满蓄削韧 | 连乘 | **不连乘，取二者较大值** | 🟡 同上 |
| 满蓄空挥收招 | 沿用 heavy 24f + `freeTail 4` | **额外 +6f 不可取消**（或空挥后 8f 内禁止再蓄力） | 🟡 承诺成本：若满蓄可以随时闪避取消，按住不放就变成零风险动作 |
| 满蓄期间移速 | 无限制 | **≤ 该职业 walk 的 60%** | 🟡 防止"边蓄力边追击"变成无成本压制 |
| 满蓄期间的减伤 | 无 | **保持无**（最多 20%，且只覆盖蓄力段） | 🟢 永劫给 30% 减伤；但本项目霸体已给"免轻击僵直"（🟢 代码语义），**两者叠加会超模**（🟡）。若一定要加，取 20% 且不覆盖判定段 |
| 满蓄命中的顿帧 | 走 `tierMul.heavy = 1.5` | **改为节点级固定 8f** | 🟡 与代码里 `guardCrush:8 / parry:12 / execute:10` 的"节点级反馈"约定一致，避免被 6f 常规上限压掉，让"这一刀不一样"看得见 |
| 满蓄松手 | 无宽限 | **+2f 宽限**（12f 阈值 → 实际 12~14f 都算满蓄） | 🟡 处理 negative edge（🟢 术语来源 [infil.net](https://glossary.infil.net/?t=Negative%20Edge)）：玩家在满蓄瞬间松手会因松手延迟被判成"未满"，产生"我明明满了"的挫败 |

### 7.3 必须修正的一处设计叙事：`armorFrom = 4` 与"轻击克蓄力" 🟡

代码注释写：「留 4 帧'未成形'窗口，轻击可以打断起手——这正是'轻击克蓄力'的实现方式」。

**但按现有帧数据算不通**：
- 轻击 l1 是 `6/3/9`，命中最早发生在**第 7 帧**（探针也是这么算的：`输入到命中首次可能 = startup + 1`）
- 霸体从**第 4 帧**起
- → **第 7 帧 ≥ 第 4 帧，霸体早就成了**。所以"双方同时起手"时，**轻击打不断蓄力**；蓄力方会硬吃这一下（叠加受击），然后打出 296 伤害。

**所以那 4 帧窗口在实战中只对"对手已经先出手"的情况有效**——它是一个**预判窗口**，不是**反应窗口**。

**两个选项，二选一，不能既要又要：**

- **方案 A（推荐，服务"抑制连点"）**：`armorFrom` **保持 4f**。承认"轻击克蓄力"只在**预判**下成立，把克制蓄力的答案**唯一地交给振刀**。同时**改掉代码注释的措辞**（从"轻击可以打断起手"改为"轻击只有在先手时才能打断蓄力"）。这与永劫的三角闭环一致（🟢 振刀克蓝霸体）。
- **方案 B（若坚持轻击能反应性打断）**：`armorFrom` 提到 **8f 以上**。代价是：**同时起手的轻击会赢过蓄力** → 而"连点轻击"的人恰好总在早出招，**蓄力就失去了抑制作用**，与本轮的设计目标直接冲突。

### 7.4 削韧倍率：当前是"单击必破防"，建议改成"两拍破防" 🟡

这是我在代码里算出来的具体风险（🟢 数据来自代码，🟡 结论是我的推断）：

满蓄斩的削韧 = `heavy.poise 38 × 职业 poiseScale × 1.8(满蓄) × 1.8(guardCrush 打格挡)`

| 职业 | poiseScale | 未格挡削韧 | **打格挡削韧** | 结果 |
|---|---|---|---|---|
| 执锐 | 1.00 | 68.4 | **123.1** | **一击破满韧格挡（100）** |
| 重锋 | 1.44 | 98.5 | **177.3** | **一击破，且严重溢出** |
| 影梭 | 0.80 | 54.7 | 98.5 | 差 1.5 点不破（临界） |
| 长策 | 0.96 | 65.7 | **118.2** | **一击破** |

**问题**：4 个职业里 3 个可以**一发满蓄就把满韧性格挡直接打崩**，而且是溢出式打崩。这让"格挡"在面对蓄力时**等于不存在**，防守方的选择被压缩成"闪避或振刀"，战斗反而更极端。

**建议（🟡）**：
1. 满蓄削韧倍率 **×1.8 → ×1.3**（38 → 49.4）
2. 满蓄加成与 guardCrush **不连乘，取较大值**（或直接设硬护栏：**单段攻击最多造成 95 点削韧**，永不单击破满韧格挡）
3. 目标态：打格挡 **88.9 < 100**，即"**需要两次**（或一次残韧）才能破防" → 破防变成一个**两拍的过程**，防守方第一次格挡后仍有一次决策机会

### 7.5 被什么打断 / 如何克制（把闭环写全）🟢+🟡

| 手段 | 是否克制满蓄斩 | 依据 |
|---|---|---|
| 轻击连点 | **不克制**（会被硬吃） | 🟢 这就是设计目标（对应永劫"蓝霸体克普攻"） |
| **振刀/弹反** | **强克制**（唯一硬解） | 🟢 永劫 [Focus 页](https://old.naraka.wiki/en/Focus) "Can be countered" |
| 闪避 | 克制（20f 含无敌帧，需预判） | 🟡 |
| 重击/上挑/绝技 | 需要明确规则 | 🟡 建议：**上挑与绝技（tier heavy/ult）可穿透满蓄霸体**，与项目现有"霸体只挡轻档"的规则一致（🟢 代码 `armorHolds = armored && move.tier === 'light' && !move.guardCrush`） |
| 被弹反后的惩罚 | 应有"兵刃脱手" | 🔴 **具体持续时间未查到**（见第 3 节）。建议先按 **18~24 帧硬直 + 掉落武器 60f 不可用**做一版，用 `CHARGESTAT` 验证后再调（🟡 **纯推断值，不是来源数值**） |

**关于弹反窗口**：现有"弹反窗口 8 帧"若是对满蓄斩同样 8 帧，考虑到永劫振刀起手就要 15f（🟢），8f 窗口其实是**更宽松**的。**建议不要为了蓄力再放宽弹反窗口**；而要保证"看到蓝光 → 振刀"在 8 帧内可行（即弹反输入到判定 ≤2f）。

### 7.6 用探针验收（这才算落地）🟡

项目已有 `CHARGESTAT = { 起手, 满蓄, 掉落, 打断, 命中, 架崩, 被格挡, 被弹反, 被毙 }`，建议直接把它变成验收门槛：

| 指标 | 目标 | 说明 |
|---|---|---|
| `满蓄 / 起手` | **30%~60%** | 太低 = 没人用（机制白做）；太高 = 变成主循环，压制了轻击连段 |
| `打断 / 起手` | **> 0** | 🟡 **若恒为 0，说明 `armorFrom=4` 的"未成形窗口"是死代码**——要么按 7.3 方案 B 改帧数，要么删掉这个说法。这是本轮最应该被数据检验的一条 |
| `被弹反 / 满蓄` | **10%~35%** | 太低 = 蓄力无解（对峙风险）；太高 = 玩家不敢用 |
| 对称极差 | **≤ 8.0pp** | 沿用项目历史基准（R3/R8 的达标线） |
| 连点轻击方 vs 蓄力方胜率 | 蓄力方 **55%~60%** | 证明"抑制连点"有效，但不能一边倒（>65% 说明蓄力成了唯一解） |

---

## 8. 来源清单

**已读取正文（可信）**
- [NARAKA 社区 Wiki · Focus Types](https://old.naraka.wiki/en/Focus)（蓝/紫/金/振刀/终极/极限霸体全套规则、30% 减伤、对刀、克制链）
- [NARAKA 社区 Wiki · Combat](https://old.naraka.wiki/en/Combat)（振刀起手帧表：复合/快捷 15f、剪式 10f、蹲跳 20f、冲刺复合 7f）
- [NARAKA 社区 Wiki · Weapons / Greatsword](https://old.naraka.wiki/en/Weapons/Greatsword)（磐石架势 90% 减伤、30~72 帧反击窗口、220° 覆盖、Regular/Invincible 区分、三段蓄力 Stage 1/2/3、振刀反击 2.90×攻击力）
- [NARAKA 社区 Wiki · Inputs & Input Buffering](https://old.naraka.wiki/en/Input-Buffering)（输入在**判定帧**内被缓存；缓存只可替换不可取消；低帧率优势差）
- [NARAKA 社区 Wiki · Character States](https://old.naraka.wiki/en/Character-States)（I-Frames、Stun、Freeze 等状态）

**已定位但未读正文（仅作为线索，正文数值未引用）**
- [Ubisoft 官方 · For Honor: Public Test – Meta Changes](https://www.ubisoft.com/en-au/game/for-honor/news-updates/1IZoiczWorTTTsrEYprgzR/public-test-meta-changes)
- [The Fighting Game Glossary · Negative Edge](https://glossary.infil.net/?t=Negative%20Edge)
- [Epic Fight 官方文档](https://epicfight-docs.readthedocs.io/)／[Gameplay](https://epicfight-docs.readthedocs.io/ja/Misc/Gameplay/)／[Skills](https://epicfight-docs.readthedocs.io/ja/Misc/Gameplay/skills/)
- [Modrinth · Better Combat](https://modrinth.com/mod/better-combat)／[MC百科 · Better Combat](https://www.mcmod.cn/class/7110.html)／[Better Combat 重生 config 汉化](https://www.mcmod.cn/post/2068.html)
- [bilibili · 单排顶尖玩家的蓄力理解丨1.0 1.2 1.5？](https://www.bilibili.com/opus/716554107405467734)（疑似三档蓄力秒数，**未验证**）
- [九游 · 怪物猎人世界三段大剑攻击蓄力伤害详解](https://www.9game.cn/gwlrsj/2040097.html)（MHW 蓄力数值线索，**未读取**）

**低质量来源（只用于确认"机制存在"，不用于数值）**
- [九游 · 《永劫无间》振刀作用是什么](https://www.9game.cn/news/5629872.html)（振刀打掉武器、可拾取、无武器伤害降低；**无时长**）

**项目内部依据**
- `作品集-雷火战斗策划\原型\止戈-战斗原型-3D.html`（`CHARGE` 常量、共享帧数据、`CANCEL`/`POISE`/`HITSTOP` 常量、`CHARGESTAT` 探针）
- [游戏手感（下）· 技能时间轴 / 取消段 / 辅助转向 / 预输入](https://www.gameres.com/898209.html)（项目预输入 0.2~0.3s 的依据；**注意这是预输入窗口，不是蓄力阈值**）

---

## 9. 明确的空白清单（下一轮要补的）

1. 🔴 《永劫无间》**满蓄耗时**的确切秒数/帧数（官方未公布；需实测或读视频源）
2. 🔴 振刀成功后**兵刃脱手/武器不可用的持续时间**
3. 🔴 《怪物猎人》大剑三段蓄力、《街霸》蓄力技、《只狼》一字斩的**确切时间**
4. 🔴 **"按下 → 判定生效"的推荐延迟（毫秒）** 的权威数值
5. 🔴 For Honor 防守型 meta 的**具体补丁改动与结果**（页面已定位，需读正文）
6. 🔴 Epic Fight / Better Combat 的**体力与蓄力具体数值**（需读 Compendium 武器页与 config 汉化帖）
