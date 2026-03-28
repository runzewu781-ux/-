from flask import Flask, request, redirect, url_for
import random
import json
import base64
import copy

app = Flask(__name__)

# ========================
# 基础配置
# ========================

LEVELS = {
    "group": {
        "name": "小组赛",
        "self_mistake_prob": 0.15,
        "up_scale": 1.0,
        "down_scale": 1.0,
        "initial_anger": 0,
        "anger_floor": 0,
    },
    "knockout": {
        "name": "淘汰赛",
        "self_mistake_prob": 0.22,
        "up_scale": 1.35,
        "down_scale": 0.75,
        "initial_anger": 15,
        "anger_floor": 10,
    },
    "final": {
        "name": "决赛",
        "self_mistake_prob": 0.30,
        "up_scale": 1.45,
        "down_scale": 0.50,
        "initial_anger": 30,
        "anger_floor": 20,
    },
}

NEXT_LEVEL = {
    "group": "knockout",
    "knockout": "final",
    "final": None,
}

LINEUPS = {
    "group": "前锋：王楷硕、钱文伟、谭琦｜中场：吾尔肯、孙奕文、洛桑罗布｜后卫：杨云帆、张明阳、田彬阳、夏绎博｜门将：伍彦名",
    "knockout": "前锋：钱文伟、谭琦、陈勇旭｜中场：吾尔肯、孙奕文、洛桑罗布｜后卫：吴杨楚涵、向家剡、张明阳、田彬阳｜门将：伍彦名",
    "final": "前锋：王楷硕、陈勇旭、程晨｜中场：吾尔肯、孙奕文、洛桑罗布｜后卫：杨云帆、夏绎博、吴杨楚涵、向家剡｜门将：伍彦名",
}

# ========================
# 球场可视化数据
# ========================

# 球员默认坐标 (x%, y%)  x=左右  y=0对方球门..100我方球门
PLAYER_POSITIONS = {
    "group": {
        "伍彦名": ((50, 93), "gk"),
        "杨云帆": ((18, 76), "df"),
        "张明阳": ((40, 76), "df"),
        "田彬阳": ((62, 76), "df"),
        "夏绎博": ((82, 76), "df"),
        "吾尔肯": ((50, 52), "mf"),
        "孙奕文": ((25, 55), "mf"),
        "洛桑罗布": ((75, 55), "mf"),
        "王楷硕": ((25, 28), "fw"),
        "钱文伟": ((50, 22), "fw"),
        "谭琦": ((75, 28), "fw"),
    },
    "knockout": {
        "伍彦名": ((50, 93), "gk"),
        "吴杨楚涵": ((18, 76), "df"),
        "向家剡": ((40, 76), "df"),
        "张明阳": ((62, 76), "df"),
        "田彬阳": ((82, 76), "df"),
        "吾尔肯": ((50, 52), "mf"),
        "孙奕文": ((25, 55), "mf"),
        "洛桑罗布": ((75, 55), "mf"),
        "钱文伟": ((25, 28), "fw"),
        "谭琦": ((50, 22), "fw"),
        "陈勇旭": ((75, 28), "fw"),
    },
    "final": {
        "伍彦名": ((50, 93), "gk"),
        "杨云帆": ((18, 76), "df"),
        "夏绎博": ((40, 76), "df"),
        "吴杨楚涵": ((62, 76), "df"),
        "向家剡": ((82, 76), "df"),
        "吾尔肯": ((50, 52), "mf"),
        "孙奕文": ((25, 55), "mf"),
        "洛桑罗布": ((75, 55), "mf"),
        "王楷硕": ((25, 28), "fw"),
        "陈勇旭": ((50, 22), "fw"),
        "程晨": ((75, 28), "fw"),
    },
}

# 阵型偏移 (dx, dy)
SCENE_OFFSETS = {
    "default":   {"gk": (0, 0),  "df": (0, 0),   "mf": (0, 0),   "fw": (0, 0)},
    "defending": {"gk": (0, 2),  "df": (0, 6),   "mf": (0, 12),  "fw": (0, 18)},
    "attacking": {"gk": (0, -3), "df": (0, -12), "mf": (0, -10), "fw": (0, -8)},
    "counter":   {"gk": (0, 2),  "df": (0, 4),   "mf": (0, 14),  "fw": (0, 20)},
    "celebrate": {"gk": (0, -15),"df": (0, -22), "mf": (0, -5),  "fw": (0, 12)},
}

# 事件类别 → (阵型, 球坐标)
CATEGORY_SCENES = {
    "传球失误":     ("counter",   (72, 18)),
    "被断球":       ("counter",   (65, 45)),
    "不听指挥":     ("default",   (50, 50)),
    "射门偏出":     ("attacking", (48, 8)),
    "裁判判罚犯规": ("default",   (55, 55)),
    "被判点球":     ("defending", (50, 85)),
    "捡球失误":     ("default",   (8, 50)),
    "独带不传球":   ("attacking", (32, 30)),
    "教练指挥分歧": ("default",   (50, 50)),
    "被进球":       ("defending", (50, 92)),
    "我方进球":     ("celebrate", (50, 8)),
    "成功防守":     ("defending", (42, 72)),
    "精彩配合":     ("attacking", (38, 32)),
    "决赛危机":     ("defending", (60, 68)),
    "吾尔肯失误":   ("counter",   (58, 58)),
}

# 对方球员默认坐标（对方GK在上方，4-3-3）
OPPONENT_POSITIONS = {
    "OPP-GK": ((50, 7), "gk"),
    "OPP-LB": ((82, 24), "df"),
    "OPP-CB1": ((62, 22), "df"),
    "OPP-CB2": ((38, 22), "df"),
    "OPP-RB": ((18, 24), "df"),
    "OPP-LM": ((75, 42), "mf"),
    "OPP-CM": ((50, 45), "mf"),
    "OPP-RM": ((25, 42), "mf"),
    "OPP-LW": ((72, 68), "fw"),
    "OPP-ST": ((50, 72), "fw"),
    "OPP-RW": ((28, 68), "fw"),
}

# 对方阵型偏移（与我方相反：我方进攻→对方回撤，我方防守→对方前压）
OPPONENT_SCENE_OFFSETS = {
    "default":   {"gk": (0, 0),  "df": (0, 0),   "mf": (0, 0),   "fw": (0, 0)},
    "defending": {"gk": (0, -2), "df": (0, -5),  "mf": (0, -8),  "fw": (0, -12)},
    "attacking": {"gk": (0, 2),  "df": (0, 8),   "mf": (0, 10),  "fw": (0, 6)},
    "counter":   {"gk": (0, 1),  "df": (0, 5),   "mf": (0, 8),   "fw": (0, 6)},
    "celebrate": {"gk": (0, 3),  "df": (0, 8),   "mf": (0, 4),   "fw": (0, -10)},
}

# 怒气值设计原则：
# A类（双选都涨怒）：不听指挥、被判点球、独带不传球、被进球 → 发火事件
# B类（一涨一降）：传球失误、被断球、射门偏出、裁判判罚、捡球失误、教练分歧
# C类（双选都降怒）：我方进球、成功防守、精彩配合
# 整体发火:降火 ≈ 5:3

GROUP_EVENT_POOL = [
    # ---- B类 传球失误 ----
    {
        "category": "传球失误",
        "description": "中场孙奕文接吾尔肯分球后，向前场传球力度过大，前锋钱文伟未能追上，球直接出了边线。",
        "options": [
            {"text": "立刻回追补防，减少对方反击机会", "anger_change": (2, 4)},
            {"text": "当场指责孙奕文传球不用心", "anger_change": (6, 9)},
        ],
    },
    {
        "category": "传球失误",
        "description": "后卫杨云帆后场接门将伍彦名传球，横传力度过轻，被对方前锋伸脚拦截，险些造成单刀。",
        "options": [
            {"text": "快速落位补防，化解门前危机", "anger_change": (4, 7)},
            {"text": "大声呵斥杨云帆低级失误", "anger_change": (9, 13)},
        ],
    },
    {
        "category": "传球失误",
        "description": "洛桑罗布中场边路拿球，想斜传禁区找王楷硕，结果传球被对方后卫伸脚挡出底线。",
        "options": [
            {"text": "快速跑向角球区，准备开角球进攻", "anger_change": (1, 3)},
            {"text": "抱怨洛桑罗布传球角度太离谱", "anger_change": (5, 8)},
        ],
    },
    {
        "category": "传球失误",
        "description": "前锋谭琦边路拿球回做，想传给插上的吾尔肯，结果力度太小，直接被对方中场断下。",
        "options": [
            {"text": "立刻上抢逼抢，尝试夺回球权", "anger_change": (3, 5)},
            {"text": "当场喊谭琦传球能不能用点力", "anger_change": (7, 10)},
        ],
    },
    # ---- B类 被断球 ----
    {
        "category": "被断球",
        "description": "前锋王楷硕前场拿球，面对对方两名防守球员执意过人，被对方轻松断球，对方立刻发起反击。",
        "options": [
            {"text": "中场队友集体落位补防", "anger_change": (6, 9)},
            {"text": "站在原地指责王楷硕独带不传球", "anger_change": (11, 15)},
        ],
    },
    {
        "category": "被断球",
        "description": "后卫向家剡后场传球拖沓，连续两次假动作晃人，被对方前锋抢断，直扑我方禁区。",
        "options": [
            {"text": "洛桑罗布回防犯规化解进攻", "anger_change": (8, 12)},
            {"text": "怒斥向家剡玩火自焚", "anger_change": (14, 18)},
        ],
    },
    {
        "category": "被断球",
        "description": "孙奕文中场拿球转身时，被对方球员从身后捅球抢断，对方快速打反击形成2打1。",
        "options": [
            {"text": "全速回追，和后卫配合防守", "anger_change": (5, 8)},
            {"text": "指责孙奕文转身不看身后球员", "anger_change": (10, 14)},
        ],
    },
    {
        "category": "被断球",
        "description": "钱文伟禁区前沿拿球想扣球过人，被对方后卫直接断球，对方门将手抛球发起快攻。",
        "options": [
            {"text": "快速回撤到中场，组织防守", "anger_change": (5, 8)},
            {"text": "摊手抱怨钱文伟处理球太犹豫", "anger_change": (9, 13)},
        ],
    },
    # ---- A类 不听指挥（双选都涨怒）----
    {
        "category": "不听指挥",
        "description": "吾尔肯大声指挥后卫杨云帆后场长传找前插的前锋，杨云帆执意选择短传倒脚，被对方逼抢导致球权丢失。",
        "options": [
            {"text": "强压怒火，快速回防化解局面", "anger_change": (8, 12)},
            {"text": "冲杨云帆大喊，质问他为什么不听指挥", "anger_change": (17, 22)},
        ],
    },
    {
        "category": "不听指挥",
        "description": "吾尔肯示意前锋谭琦往禁区中路跑位拉扯防守，谭琦却执意拉到边路，吾尔肯直塞无人接应出底线。",
        "options": [
            {"text": "咬牙忍下，重新组织进攻", "anger_change": (7, 11)},
            {"text": "当场质问谭琦为什么不按战术跑位", "anger_change": (16, 20)},
        ],
    },
    {
        "category": "不听指挥",
        "description": "吾尔肯指挥洛桑罗布中场拦截后立刻出球，洛桑罗布却执意带球推进，结果被对方包夹断球。",
        "options": [
            {"text": "憋住气，快速回防补位", "anger_change": (9, 13)},
            {"text": "冲洛桑罗布大喊战术执行不到位", "anger_change": (15, 19)},
        ],
    },
    # ---- B类 射门偏出 ----
    {
        "category": "射门偏出",
        "description": "吾尔肯送出精准直塞，前锋王楷硕形成单刀机会，射门角度太偏擦立柱出底线。",
        "options": [
            {"text": "上前拍背鼓励，下次把握机会", "anger_change": (-12, -8)},
            {"text": "当场暴怒，指责王楷硕浪费绝佳机会", "anger_change": (14, 18)},
        ],
    },
    {
        "category": "射门偏出",
        "description": "前锋钱文伟禁区前沿无人盯防远射，结果直接踢飞高出横梁。",
        "options": [
            {"text": "示意队友回撤防守", "anger_change": (4, 7)},
            {"text": "摊手抱怨钱文伟脚法太离谱", "anger_change": (9, 13)},
        ],
    },
    {
        "category": "射门偏出",
        "description": "谭琦边路突破下底传中，洛桑罗布中路头球攻门，结果顶得太正被对方门将没收。",
        "options": [
            {"text": "鼓励洛桑罗布，头球争顶很积极", "anger_change": (-10, -6)},
            {"text": "抱怨洛桑罗布头球不会甩头攻门", "anger_change": (9, 13)},
        ],
    },
    {
        "category": "射门偏出",
        "description": "孙奕文中场远射，皮球打在对方后卫身上折射，稍稍偏出左侧门柱。",
        "options": [
            {"text": "上前和孙奕文击掌，鼓励继续远射", "anger_change": (-8, -5)},
            {"text": "说孙奕文射门脚法再控制一点", "anger_change": (6, 10)},
        ],
    },
    # ---- B类 裁判判罚犯规 ----
    {
        "category": "裁判判罚犯规",
        "description": "中场洛桑罗布中场拦截时抬脚过高，裁判吹罚技术犯规，对方获得中场定位球。",
        "options": [
            {"text": "安抚洛桑罗布，组织人墙防守", "anger_change": (-4, -2)},
            {"text": "冲裁判大声抗议，认为判罚过重", "anger_change": (5, 8)},
        ],
    },
    {
        "category": "裁判判罚犯规",
        "description": "后卫张明阳禁区前沿防守时，手臂轻微碰到对方球员，裁判吹罚推人犯规，对方获前场定位球。",
        "options": [
            {"text": "和队友沟通人墙站位，专注防守", "anger_change": (-3, -1)},
            {"text": "向裁判解释只是轻微接触，判罚不公", "anger_change": (5, 8)},
        ],
    },
    {
        "category": "裁判判罚犯规",
        "description": "王楷硕前场反抢时，从侧后方碰到对方后卫，裁判吹罚拉人犯规，进攻被中断。",
        "options": [
            {"text": "示意王楷硕下次反抢注意动作", "anger_change": (-3, -1)},
            {"text": "冲裁判喊反抢正常动作，不该吹罚", "anger_change": (4, 7)},
        ],
    },
    # ---- A类 被判点球（双选都涨怒）----
    {
        "category": "被判点球",
        "description": "后卫张明阳禁区内防守对方单刀球员时，伸手拉拽对方球衣，裁判果断吹罚点球。",
        "options": [
            {"text": "强压怒火，安抚队友准备防守点球", "anger_change": (5, 9)},
            {"text": "围堵裁判大声理论，认为判罚不公", "anger_change": (15, 20)},
        ],
    },
    {
        "category": "被判点球",
        "description": "田彬阳禁区内解围时，抬脚碰到对方倒地球员，裁判吹罚抬脚过高，判罚点球。",
        "options": [
            {"text": "咬牙安抚田彬阳，专注点球防守", "anger_change": (6, 10)},
            {"text": "怒斥裁判没看清动作，胡乱判罚", "anger_change": (14, 18)},
        ],
    },
    {
        "category": "被判点球",
        "description": "夏绎博禁区内防守传中球时，身后推了对方前锋一把，裁判吹罚推人犯规，判罚点球。",
        "options": [
            {"text": "憋着气组织人墙，提醒伍彦名判断方向", "anger_change": (5, 9)},
            {"text": "和裁判争辩，认为对方假摔", "anger_change": (13, 17)},
        ],
    },
    # ---- B类 捡球失误 ----
    {
        "category": "捡球失误",
        "description": "球出边线后，场边替补球员捡球太慢，耽误了我方快速反击的最佳时机。",
        "options": [
            {"text": "朝场边喊一声，提醒快点捡球", "anger_change": (-4, -2)},
            {"text": "当场怒斥场边球员不懂比赛节奏", "anger_change": (4, 7)},
        ],
    },
    {
        "category": "捡球失误",
        "description": "对方射门被伍彦名扑出底线，场边球员半天没把角球扔进来，对方已全部落位防守。",
        "options": [
            {"text": "挥手示意场边快送球，继续进攻", "anger_change": (-3, -1)},
            {"text": "抱怨场边球员磨磨蹭蹭，影响进攻", "anger_change": (4, 7)},
        ],
    },
    {
        "category": "捡球失误",
        "description": "我方前锋突破被对方铲出边线，场边球员捡球后扔给了对方球员，错失快速发球机会。",
        "options": [
            {"text": "无奈摇头，重新向裁判要球", "anger_change": (-2, 0)},
            {"text": "大声指责场边球员传错球，太业余", "anger_change": (5, 8)},
        ],
    },
    # ---- A类 独带不传球（双选都涨怒）----
    {
        "category": "独带不传球",
        "description": "前锋谭琦前场拿球后一直盘带，无视空位的钱文伟，最终被对方两名防守球员包夹断球。",
        "options": [
            {"text": "强忍怒气，快速回撤防守", "anger_change": (7, 11)},
            {"text": "当场大喊，质问谭琦为什么不传球", "anger_change": (16, 20)},
        ],
    },
    {
        "category": "独带不传球",
        "description": "王楷硕禁区左侧拿球，吾尔肯和钱文伟都在禁区内空位，他却执意射门被门将扑出。",
        "options": [
            {"text": "憋住，快速跑向门前准备补射", "anger_change": (6, 10)},
            {"text": "质问王楷硕为什么不传球，太独了", "anger_change": (14, 18)},
        ],
    },
    {
        "category": "独带不传球",
        "description": "杨云帆后场拿球后，一路带球推进到中场，无视空位的洛桑罗布，结果被对方断球反击。",
        "options": [
            {"text": "深吸一口气，和后卫配合化解反击", "anger_change": (7, 11)},
            {"text": "怒斥杨云帆后场带球太鲁莽", "anger_change": (15, 19)},
        ],
    },
    # ---- B类 教练指挥分歧 ----
    {
        "category": "教练指挥分歧",
        "description": "场边教练示意吾尔肯回撤到后卫线前参与防守，吾尔肯认为应该压上进攻。",
        "options": [
            {"text": "听从教练指挥，回撤防守", "anger_change": (2, 4)},
            {"text": "坚持自己的判断，继续压上进攻", "anger_change": (6, 9)},
        ],
    },
    {
        "category": "教练指挥分歧",
        "description": "教练示意换下前锋钱文伟，吾尔肯认为钱文伟状态不错，换人会中断进攻节奏。",
        "options": [
            {"text": "服从教练换人安排，和钱文伟击掌", "anger_change": (3, 5)},
            {"text": "走到场边和教练沟通，希望暂缓换人", "anger_change": (6, 9)},
        ],
    },
    {
        "category": "教练指挥分歧",
        "description": "教练让全队改打五后卫死守，吾尔肯认为应该继续保持进攻阵型，扩大优势。",
        "options": [
            {"text": "听从教练战术，指挥队友回撤防守", "anger_change": (2, 4)},
            {"text": "坚持进攻阵型，继续前插组织进攻", "anger_change": (5, 8)},
        ],
    },
    # ---- A类 被进球（双选都涨怒）----
    {
        "category": "被进球",
        "description": "对方通过边路快速反击，传中到禁区，前锋头球破门，我方暂时落后。",
        "options": [
            {"text": "强行压制怒气，拍手示意队友反攻", "anger_change": (4, 8)},
            {"text": "当场怒斥防守失位的后卫球员", "anger_change": (16, 20)},
        ],
    },
    {
        "category": "被进球",
        "description": "对方中场远射，皮球打在田彬阳身上折射，伍彦名判断失误，皮球入网。",
        "options": [
            {"text": "咬牙安抚田彬阳，示意这是意外", "anger_change": (3, 7)},
            {"text": "抱怨后卫没有封堵远射角度", "anger_change": (14, 18)},
        ],
    },
    {
        "category": "被进球",
        "description": "对方角球开出，中路球员无人盯防头球破门，我方防守漏人严重。",
        "options": [
            {"text": "憋住气，指挥队友重新布置防守", "anger_change": (4, 8)},
            {"text": "怒斥防守球员盯人不紧，业余失误", "anger_change": (15, 19)},
        ],
    },
    # ---- C类 我方进球（双选都降怒）----
    {
        "category": "我方进球",
        "description": "吾尔肯送出精准直塞，前锋钱文伟单刀冷静推射破门，我方取得领先。",
        "options": [
            {"text": "冲上去拥抱钱文伟，和队友一起庆祝", "anger_change": (-38, -28)},
            {"text": "简单和队友击掌，专注比赛扩大优势", "anger_change": (-28, -18)},
        ],
    },
    {
        "category": "我方进球",
        "description": "谭琦边路突破下底传中，王楷硕中路抢点铲射破门，我方再下一城。",
        "options": [
            {"text": "和队友围在一起庆祝，气氛热烈", "anger_change": (-36, -26)},
            {"text": "快速跑回中圈，准备继续开球进攻", "anger_change": (-26, -16)},
        ],
    },
    {
        "category": "我方进球",
        "description": "吾尔肯中场拿球后远射，皮球直挂死角破门，世界波打破僵局。",
        "options": [
            {"text": "队友围上来庆祝，挥手向球迷致意", "anger_change": (-42, -32)},
            {"text": "简单举手庆祝，示意队友专注比赛", "anger_change": (-32, -22)},
        ],
    },
    # ---- C类 成功防守（双选都降怒）----
    {
        "category": "成功防守",
        "description": "对方单刀直面门将，伍彦名奋力侧扑，将球稳稳抱住，化解绝佳破门机会。",
        "options": [
            {"text": "冲伍彦名竖大拇指，夸赞精彩扑救", "anger_change": (-22, -16)},
            {"text": "全队一起鼓掌鼓劲，快速组织进攻", "anger_change": (-18, -12)},
        ],
    },
    {
        "category": "成功防守",
        "description": "对方前锋禁区内射门，张明阳飞身堵枪眼，将球挡出底线，化解门前危机。",
        "options": [
            {"text": "上前拍张明阳肩膀，夸赞铁血防守", "anger_change": (-21, -15)},
            {"text": "快速跑向角球区，组织防守角球", "anger_change": (-16, -10)},
        ],
    },
    {
        "category": "成功防守",
        "description": "对方边路快速突破，夏绎博从身后精准放铲，将球铲出边线，成功断球。",
        "options": [
            {"text": "和夏绎博击掌，夸赞放铲漂亮", "anger_change": (-22, -16)},
            {"text": "示意队友注意对方边路进攻，加强防守", "anger_change": (-17, -11)},
        ],
    },
    # ---- C类 精彩配合（双选都降怒）----
    {
        "category": "精彩配合",
        "description": "孙奕文、洛桑罗布、吾尔肯三人中场连续一脚传球，轻松撕开对方防线，创造绝佳进攻机会。",
        "options": [
            {"text": "大声为队友的精彩配合鼓掌叫好", "anger_change": (-22, -16)},
            {"text": "继续前插，示意队友继续传球", "anger_change": (-18, -12)},
        ],
    },
    {
        "category": "精彩配合",
        "description": "后场杨云帆长传，谭琦边路头球摆渡，吾尔肯中路凌空抽射被门将扑出，配合行云流水。",
        "options": [
            {"text": "和队友击掌，夸赞配合太流畅", "anger_change": (-20, -14)},
            {"text": "快速跑向门前，准备补射", "anger_change": (-16, -10)},
        ],
    },
    {
        "category": "精彩配合",
        "description": "钱文伟禁区内回做，王楷硕脚后跟传球，吾尔肯插上射门被挡，三人小范围配合堪称完美。",
        "options": [
            {"text": "为队友的默契配合大喊叫好", "anger_change": (-21, -15)},
            {"text": "示意队友继续保持这样的配合节奏", "anger_change": (-17, -11)},
        ],
    },
]

# 决赛专属危机事件（time >= 70 时 40% 概率触发，双选都涨怒）
FINAL_CRITICAL_EVENTS = [
    {
        "category": "决赛危机",
        "description": "决赛关键时刻，田彬阳和夏绎博同时回防却彼此干扰，被对方前锋轻松过掉形成单刀。",
        "options": [
            {"text": "强压怒火，大声指挥门将迎球封堵", "anger_change": (10, 16)},
            {"text": "冲两人大喊，质问防守配合为何这么差", "anger_change": (22, 30)},
        ],
    },
    {
        "category": "决赛危机",
        "description": "决赛压哨阶段，孙奕文连续三次传球失误导致对方多次反击威胁，全队陷入混乱。",
        "options": [
            {"text": "咬牙让孙奕文简化传球，保持稳定", "anger_change": (12, 18)},
            {"text": "当场大喊，让孙奕文冷静还是换人", "anger_change": (24, 32)},
        ],
    },
    {
        "category": "决赛危机",
        "description": "决赛最后阶段，吴杨楚涵禁区前沿慌乱解围，皮球直接踢出界外，丧失最后一次进攻机会。",
        "options": [
            {"text": "深吸一口气，示意队友重新组织防守", "anger_change": (11, 17)},
            {"text": "怒斥吴杨楚涵处理球太保守，影响全队", "anger_change": (23, 31)},
        ],
    },
]

SELF_MISTAKE_EVENTS = [
    {
        "description": "吾尔肯中场拿球时停球失误，被对方前锋断球并发起反击。",
        "ranges": {
            "group": (28, 38),
            "knockout": (38, 50),
            "final": (50, 62),
        },
    },
    {
        "description": "吾尔肯前场远射时踢空，被对方打出快速反击。",
        "ranges": {
            "group": (20, 30),
            "knockout": (30, 42),
            "final": (42, 55),
        },
    },
    {
        "description": "吾尔肯后场回传门将时力度过大，皮球直接滚出底线，送给对方角球。",
        "ranges": {
            "group": (24, 34),
            "knockout": (34, 46),
            "final": (46, 58),
        },
    },
]

# ========================
# 工具函数
# ========================

def encode_state(state):
    return base64.urlsafe_b64encode(json.dumps(state, ensure_ascii=False).encode()).decode()


def decode_state(data):
    return json.loads(base64.urlsafe_b64decode(data.encode()).decode())


def initial_progress():
    return {
        "unlocked_levels": ["group"],
        "cleared_levels": [],
    }


def normalize_progress(progress):
    unlocked = progress.get("unlocked_levels", ["group"])
    cleared = progress.get("cleared_levels", [])

    valid_keys = list(LEVELS.keys())
    unlocked = [level for level in unlocked if level in valid_keys]
    cleared = [level for level in cleared if level in valid_keys]

    if "group" not in unlocked:
        unlocked.insert(0, "group")

    progress["unlocked_levels"] = list(dict.fromkeys(unlocked))
    progress["cleared_levels"] = list(dict.fromkeys(cleared))
    return progress


def decode_progress(data):
    if not data:
        return initial_progress()
    try:
        progress = decode_state(data)
        return normalize_progress(progress)
    except Exception:
        return initial_progress()


def encode_progress(progress):
    return encode_state(normalize_progress(progress))


def extract_progress(state):
    return normalize_progress(
        {
            "unlocked_levels": state.get("unlocked_levels", ["group"]),
            "cleared_levels": state.get("cleared_levels", []),
        }
    )


def clamp_min(value, minimum=0):
    return value if value >= minimum else minimum


def format_signed(num):
    return f"{num:+d}"


def roll_range(value_range):
    low, high = value_range
    if low > high:
        low, high = high, low
    return random.randint(low, high)


def scale_anger_range(value_range, level_key):
    if level_key == "group":
        return value_range

    low, high = value_range
    scale = LEVELS[level_key]["up_scale"] if high > 0 else LEVELS[level_key]["down_scale"]
    scaled_low = int(round(low * scale))
    scaled_high = int(round(high * scale))

    if scaled_low == scaled_high:
        if scaled_high >= 0:
            scaled_high += 1
        else:
            scaled_low -= 1

    return (scaled_low, scaled_high)


def build_level_pool(level_key):
    events = []
    for item in GROUP_EVENT_POOL:
        options = []
        for option in item["options"]:
            options.append(
                {
                    "text": option["text"],
                    "anger_change": scale_anger_range(option["anger_change"], level_key),
                }
            )
        events.append(
            {
                "category": item["category"],
                "description": item["description"],
                "options": options,
            }
        )
    return events


EVENT_POOLS = {level_key: build_level_pool(level_key) for level_key in LEVELS.keys()}


def reset_event_ids(level_key):
    return list(range(len(EVENT_POOLS[level_key])))


def get_debuff(state):
    """50 分钟后且连续发火 2 次及以上，所有怒气变化额外 +5（降怒也削弱）"""
    if state.get("time", 0) < 50:
        return 0
    return 5 if state.get("consecutive_anger", 0) >= 2 else 0


def apply_anger_change(state, delta):
    floor = LEVELS[state["level"]]["anger_floor"]
    new_val = state["anger"] + delta
    state["anger"] = max(new_val, floor)
    # 更新连续发火计数
    if delta > 0:
        state["consecutive_anger"] = state.get("consecutive_anger", 0) + 1
    else:
        state["consecutive_anger"] = 0


def advance_time(state, base_minutes=10):
    # 70 分钟后进入危险时段，每次仅推进 5 分钟（压力骤增）
    minutes = 5 if state["time"] >= 70 else base_minutes
    state["time"] = min(90, state["time"] + minutes)


def check_result(state):
    anger = state["anger"]
    time = state["time"]

    if anger >= 100:
        if time < 80:
            return {
                "type": "lose",
                "headline": f"比赛失败！最终时间：{time}分钟，最终怒气值：{anger}（红牌罚下）",
                "detail": "吾尔肯怒气失控被罚下，球队遗憾输掉比赛...",
            }
        return {
            "type": "late_red_win",
            "headline": f"比赛胜利！最终时间：{time}分钟，最终怒气值：{anger}（红牌罚下，但守住了！）",
            "detail": "吾尔肯在最后阶段彻底失控，把全队骂了个遍，随即被裁判出示红牌罚下。但队友们顶住压力，最终守住了来之不易的胜利。",
        }

    if time >= 90:
        return {
            "type": "win",
            "headline": f"比赛胜利！最终时间：{time}分钟，最终怒气值：{anger}",
            "detail": "吾尔肯压制住怒火，带领球队取得胜利！",
        }

    return None


def pick_event(state):
    level = state["level"]

    if random.random() < LEVELS[level]["self_mistake_prob"]:
        state["last_category"] = "吾尔肯失误"
        event = random.choice(SELF_MISTAKE_EVENTS)
        return {
            "auto": True,
            "category": "吾尔肯失误",
            "description": event["description"],
            "anger_delta": roll_range(event["ranges"][level]),
        }

    # 决赛危机事件：决赛且时间 >= 70 时，40% 概率触发
    if level == "final" and state.get("time", 0) >= 70:
        if random.random() < 0.40:
            event = random.choice(FINAL_CRITICAL_EVENTS)
            scaled_options = []
            for option in event["options"]:
                scaled_options.append({
                    "text": option["text"],
                    "anger_change": scale_anger_range(option["anger_change"], level),
                })
            return {
                "category": event["category"],
                "description": event["description"],
                "options": scaled_options,
            }

    remaining_ids = state.get("remaining_event_ids", [])
    if not remaining_ids:
        remaining_ids = reset_event_ids(level)

    last_category = state.get("last_category", "")
    candidate_ids = [
        idx for idx in remaining_ids if EVENT_POOLS[level][idx]["category"] != last_category
    ]
    if not candidate_ids:
        candidate_ids = remaining_ids[:]

    chosen_id = random.choice(candidate_ids)
    state["remaining_event_ids"] = [idx for idx in remaining_ids if idx != chosen_id]
    state["last_category"] = EVENT_POOLS[level][chosen_id]["category"]
    return EVENT_POOLS[level][chosen_id]


# ========================
# 渲染工具
# ========================

def render_page(title, body):
    html = """
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>__TITLE__</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 860px;
            margin: 40px auto;
            padding: 0 16px;
            line-height: 1.8;
            color: #1f2328;
            background: #ffffff;
        }
        .card {
            border: 1px solid #d0d7de;
            border-radius: 12px;
            padding: 16px;
            margin: 16px 0;
            background: #f6f8fa;
        }
        .note {
            border-left: 4px solid #0969da;
            padding: 10px 14px;
            margin: 16px 0;
            background: #eef6ff;
        }
        .danger {
            border-left-color: #cf222e;
            background: #fff1f0;
        }
        .anger-warning {
            border: 2px solid #cf222e;
            border-radius: 12px;
            padding: 16px;
            margin: 16px 0;
            background: #fff1f0;
        }
        a.choice {
            display: block;
            margin: 10px 0;
            padding: 12px 14px;
            border: 1px solid #d0d7de;
            border-radius: 10px;
            text-decoration: none;
            color: #1f2328;
            background: white;
        }
        a.choice:hover {
            background: #f3f4f6;
        }
        .locked {
            display: block;
            margin: 10px 0;
            padding: 12px 14px;
            border: 1px dashed #d0d7de;
            border-radius: 10px;
            color: #57606a;
            background: #fafbfc;
        }
        .muted {
            color: #57606a;
        }
        input.share {
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
        }
        /* 球场 */
        .pitch-box { margin: 16px 0; }
        .pitch { position:relative; width:100%; max-width:420px; margin:0 auto; aspect-ratio:68/105; background:linear-gradient(180deg,#2d8a4e,#34a058 50%,#2d8a4e); border:3px solid #fff; border-radius:6px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.2); }
        .p-line { position:absolute; background:rgba(255,255,255,.6); }
        .p-half { top:50%; left:0; right:0; height:2px; }
        .p-circle { position:absolute; top:50%; left:50%; width:24%; aspect-ratio:1; border:2px solid rgba(255,255,255,.6); border-radius:50%; transform:translate(-50%,-50%); }
        .p-cdot { position:absolute; top:50%; left:50%; width:6px; height:6px; background:rgba(255,255,255,.7); border-radius:50%; transform:translate(-50%,-50%); }
        .pa-top { position:absolute; top:0; left:20%; right:20%; height:18%; border:2px solid rgba(255,255,255,.6); border-top:none; }
        .ga-top { position:absolute; top:0; left:33%; right:33%; height:8%; border:2px solid rgba(255,255,255,.6); border-top:none; }
        .pa-btm { position:absolute; bottom:0; left:20%; right:20%; height:18%; border:2px solid rgba(255,255,255,.6); border-bottom:none; }
        .ga-btm { position:absolute; bottom:0; left:33%; right:33%; height:8%; border:2px solid rgba(255,255,255,.6); border-bottom:none; }
        .goal-t { position:absolute; top:0; left:40%; right:40%; height:3px; background:#fff; }
        .goal-b { position:absolute; bottom:0; left:40%; right:40%; height:3px; background:#fff; }
        .pd { position:absolute; text-align:center; z-index:2; transform:translate(-50%,-50%); }
        .pd-i { display:flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:50%; font-size:11px; font-weight:bold; color:#fff; background:#3b82f6; border:2px solid rgba(255,255,255,.85); margin:0 auto; }
        .pd-n { display:block; font-size:8px; color:#fff; text-shadow:1px 1px 2px rgba(0,0,0,.9); white-space:nowrap; margin-top:1px; line-height:1; }
        .pd-wk .pd-i { background:#dc2626; width:30px; height:30px; font-size:15px; border-color:#fbbf24; box-shadow:0 0 10px rgba(220,38,38,.7); }
        .pd-wk .pd-n { font-weight:bold; color:#fde68a; font-size:9px; }
        .pd-wk.pd-ag .pd-i { animation:aPulse .5s ease-in-out infinite; }
        .pd-hl .pd-i { animation:hFlash .4s ease-in-out 4; box-shadow:0 0 14px rgba(251,191,36,.95); }
        .pd-op .pd-i { background:#e67e22; width:22px; height:22px; font-size:9px; border-color:rgba(255,255,255,.5); opacity:.85; }
        .pd-op .pd-n { display:none; }
        .p-ball { position:absolute; transform:translate(-50%,-50%); font-size:14px; z-index:3; filter:drop-shadow(0 2px 3px rgba(0,0,0,.5)); animation:bIn .5s ease-out both; }
        .pitch-lg { display:flex; justify-content:center; gap:14px; margin-top:6px; font-size:11px; color:#57606a; }
        @keyframes pRun { from{opacity:.3;transform:translate(calc(-50% + var(--ox,0px)),calc(-50% + var(--oy,0px)))} to{opacity:1;transform:translate(-50%,-50%)} }
        @keyframes aPulse { 0%,100%{box-shadow:0 0 10px rgba(220,38,38,.7);transform:scale(1)} 50%{box-shadow:0 0 22px rgba(220,38,38,1);transform:scale(1.15)} }
        @keyframes hFlash { 0%,100%{background:#3b82f6} 50%{background:#f59e0b;transform:scale(1.2)} }
        @keyframes bIn { from{opacity:0;transform:translate(-50%,-90%)} to{opacity:1;transform:translate(-50%,-50%)} }
    </style>
</head>
<body>
__BODY__
<script>
(function(){
  var p=document.querySelector('.pitch');if(!p)return;
  var ds=p.querySelectorAll('.pd'),bl=p.querySelector('.p-ball');
  var RNG={gk:3,df:6,mf:10,fw:12};
  ds.forEach(function(d){
    d._bx=parseFloat(d.dataset.bx);d._by=parseFloat(d.dataset.by);
    d._x=d._bx;d._y=d._by;d._r=RNG[d.dataset.r]||8;
    d.style.transition='left 2s ease-in-out,top 2s ease-in-out';
  });
  bl.style.transition='left 1.2s ease,top 1.2s ease';
  var team=[],opp=[];
  ds.forEach(function(d){if(d.classList.contains('pd-op'))opp.push(d);else team.push(d);});
  var tick=0;
  function mv(){
    ds.forEach(function(d){
      var r=d._r;
      var nx=d._bx+(Math.random()-.5)*r*2;
      var ny=d._by+(Math.random()-.5)*r*1.5;
      d.style.left=Math.max(3,Math.min(97,nx))+'%';
      d.style.top=Math.max(3,Math.min(97,ny))+'%';
      d._x=nx;d._y=ny;
    });
    tick++;var src=tick%3===0?opp:team;
    if(src.length>0){var h=src[Math.floor(Math.random()*src.length)];
    bl.style.left=h._x+'%';bl.style.top=(h._y-1.5)+'%';}
  }
  setTimeout(mv,500);setInterval(mv,2200);
})();
</script>
</body>
</html>
"""
    return html.replace("__TITLE__", title).replace("__BODY__", body)


def render_share_box(current_url):
    return f"""
<div class='card'>
    <p class='muted'>分享链接</p>
    <input class='share' value="{current_url}">
</div>
"""


def render_status(state):
    anger = state['anger']
    card_class = "anger-warning" if anger >= 70 else "card"
    warning_text = "<p style='color:#cf222e;font-weight:bold'>⚠️ 吾尔肯已接近爆发边缘！</p>" if anger >= 70 else ""
    debuff_text = ""
    if state.get("consecutive_anger", 0) >= 2:
        debuff_text = "<p style='color:#cf222e'>🔥 连续爆发状态：所有选项怒气额外 +5</p>"
    return f"""
<div class='{card_class}'>
    {warning_text}
    {debuff_text}
    <p><strong>当前关卡：</strong>{LEVELS[state['level']]['name']}</p>
    <p><strong>比赛时间：</strong>{state['time']} 分钟</p>
    <p><strong>吾尔肯怒气值：</strong>{anger}</p>
    <p><strong>阵容：</strong>{LINEUPS[state['level']]}</p>
</div>
"""


def extract_highlights(desc, level):
    return [n for n in PLAYER_POSITIONS.get(level, {}) if n in desc and n != "吾尔肯"]


def get_wuerken_emoji(anger):
    if anger >= 80: return "🤬"
    if anger >= 60: return "😡"
    if anger >= 40: return "😠"
    if anger >= 20: return "😤"
    return "😐"


def render_pitch(state, category="", description=""):
    level = state["level"]
    positions = PLAYER_POSITIONS.get(level, {})
    scene_name, ball_pos = CATEGORY_SCENES.get(category, ("default", (50, 50)))
    offsets = SCENE_OFFSETS.get(scene_name, SCENE_OFFSETS["default"])
    opp_offsets = OPPONENT_SCENE_OFFSETS.get(scene_name, OPPONENT_SCENE_OFFSETS["default"])
    highlights = extract_highlights(description, level)
    anger = state["anger"]
    wk_e = get_wuerken_emoji(anger)
    bx, by = ball_pos

    dots = ""
    idx = 0
    # 我方球员（蓝色 + 吾尔肯红色）
    for name, (pos, role) in positions.items():
        x, y = pos
        dx, dy = offsets.get(role, (0, 0))
        fx = max(5, min(95, x + dx))
        fy = max(3, min(97, y + dy))
        is_wk = name == "吾尔肯"
        cls = "pd"
        if is_wk:
            cls += " pd-wk"
            if anger >= 70:
                cls += " pd-ag"
        if name in highlights:
            cls += " pd-hl"
        ico = wk_e if is_wk else name[0]
        dots += (
            f"<div class='{cls}' data-bx='{fx}' data-by='{fy}' data-r='{role}' "
            f"style='left:{fx}%;top:{fy}%' title='{name}'>"
            f"<span class='pd-i'>{ico}</span>"
            f"<span class='pd-n'>{name}</span></div>"
        )
        idx += 1

    # 对方球员（橙色）
    for name, (pos, role) in OPPONENT_POSITIONS.items():
        x, y = pos
        dx, dy = opp_offsets.get(role, (0, 0))
        fx = max(5, min(95, x + dx))
        fy = max(3, min(97, y + dy))
        dots += (
            f"<div class='pd pd-op' data-bx='{fx}' data-by='{fy}' data-r='{role}' "
            f"style='left:{fx}%;top:{fy}%' title='对方球员'>"
            f"<span class='pd-i'>●</span>"
            f"<span class='pd-n'></span></div>"
        )
        idx += 1

    return f"""
<div class='pitch-box'>
  <div class='pitch'>
    <div class='p-line p-half'></div>
    <div class='p-circle'></div>
    <div class='p-cdot'></div>
    <div class='pa-top'></div><div class='ga-top'></div>
    <div class='pa-btm'></div><div class='ga-btm'></div>
    <div class='goal-t'></div><div class='goal-b'></div>
    <div class='p-ball' style='left:{bx}%;top:{by}%'>⚽</div>
    {dots}
    <div style='position:absolute;top:2px;width:100%;text-align:center;font-size:10px;color:rgba(255,255,255,.5)'>对方球门 ↑</div>
    <div style='position:absolute;bottom:2px;width:100%;text-align:center;font-size:10px;color:rgba(255,255,255,.5)'>↓ 我方球门</div>
  </div>
  <div class='pitch-lg'>
    <span>🔴 吾尔肯 {wk_e}</span>
    <span>🔵 队友</span>
    <span>🟠 对方</span>
    <span>⚽ 球</span>
  </div>
</div>
"""


def add_progress_on_win(progress, current_level):
    progress = normalize_progress(progress)
    if current_level not in progress["cleared_levels"]:
        progress["cleared_levels"].append(current_level)

    next_level = NEXT_LEVEL[current_level]
    if next_level and next_level not in progress["unlocked_levels"]:
        progress["unlocked_levels"].append(next_level)

    return normalize_progress(progress)


# ========================
# 路由
# ========================

@app.route("/")
def index():
    progress = decode_progress(request.args.get("progress"))
    progress_token = encode_progress(progress)

    level_cards = []
    for level_key in ["group", "knockout", "final"]:
        level_name = LEVELS[level_key]["name"]
        if level_key in progress["unlocked_levels"]:
            level_cards.append(
                f"<a class='choice' href='{url_for('start', level=level_key, progress=progress_token)}'>{level_name}</a>"
            )
        else:
            level_cards.append(f"<div class='locked'>{level_name}：需通关前一关后解锁</div>")

    body = f"""
<h1>华科新闻学院足球队：吾尔肯的怒气挑战</h1>
<div class='card'>
    <p>规则说明：</p>
    <p>1. 吾尔肯怒气值初始为 0（淘汰赛 15，决赛 30），达到 100 即红牌。</p>
    <p>2. 每次选择推进 10 分钟；70 分钟后进入危险时段，每次仅推进 5 分钟。</p>
    <p>3. 80 分钟前红牌直接失败；80 分钟及以后红牌仍判定胜利（但全队会被骂一顿）。</p>
    <p>4. 连续两次选择导致怒气上涨，触发「连续爆发」buff，所有选项额外 +5 怒气。</p>
    <p>5. 淘汰赛和决赛设有怒气下限（淘汰赛 10，决赛 20），降怒无法低于此值。</p>
    <p>6. 每关使用独立事件池，同大类事件不会连续触发，抽完后自动重置。</p>
    <p>7. 任意界面都可以直接复制链接分享给群聊。</p>
</div>
<div class='card'>
    <p>选择关卡开始：</p>
    {''.join(level_cards)}
</div>
{render_share_box(request.url)}
"""
    return render_page("华科新闻学院足球队：吾尔肯的怒气挑战", body)


@app.route("/start")
def start():
    level = request.args.get("level")
    progress = decode_progress(request.args.get("progress"))

    if level not in LEVELS:
        return "关卡参数错误", 400

    if level not in progress["unlocked_levels"]:
        return "该关卡尚未解锁", 400

    state = {
        "level": level,
        "time": 0,
        "anger": LEVELS[level]["initial_anger"],
        "consecutive_anger": 0,
        "remaining_event_ids": reset_event_ids(level),
        "last_category": "",
        "last_feedback": f"比赛开始。吾尔肯站在中场，怒气值 {LEVELS[level]['initial_anger']}，知道这场球最大的对手可能就是自己的火气。",
        "unlocked_levels": progress["unlocked_levels"],
        "cleared_levels": progress["cleared_levels"],
    }

    return redirect(url_for("game", data=encode_state(state)))


@app.route("/game")
def game():
    data = request.args.get("data")
    if not data:
        return redirect(url_for("index"))

    try:
        state = decode_state(data)
    except Exception:
        return "游戏状态无效", 400

    result = check_result(state)
    if result:
        progress = extract_progress(state)
        if result["type"] != "lose":
            progress = add_progress_on_win(progress, state["level"])

        progress_token = encode_progress(progress)
        replay_link = url_for("start", level=state["level"], progress=progress_token)
        home_link = url_for("index", progress=progress_token)
        next_level = NEXT_LEVEL[state["level"]]

        next_button = ""
        if next_level and next_level in progress["unlocked_levels"]:
            next_button = f"<a class='choice' href='{url_for('start', level=next_level, progress=progress_token)}'>进入{LEVELS[next_level]['name']}</a>"

        end_scene = "我方进球" if result["type"] != "lose" else "被进球"
        end_pitch = render_pitch(state, end_scene, "")

        body = f"""
<h2>比赛结束</h2>
<div class='note danger'>
    <p><strong>{result['headline']}</strong></p>
    <p>{result['detail']}</p>
</div>
{render_status(state)}
{end_pitch}
<a class='choice' href='{replay_link}'>重玩当前关卡</a>
{next_button}
<a class='choice' href='{home_link}'>返回首页</a>
{render_share_box(request.url)}
"""
        return render_page("比赛结束", body)

    feedback_html = ""
    if state.get("last_feedback"):
        feedback_html = f"<div class='note'>{state['last_feedback']}</div>"
        state["last_feedback"] = ""

    event = pick_event(state)

    if event.get("auto"):
        apply_anger_change(state, event["anger_delta"])
        advance_time(state)
        state["last_feedback"] = (
            f"吾尔肯自身失误：{event['description']} 怒气值{format_signed(event['anger_delta'])}，"
            f"比赛时间来到{state['time']}分钟。"
        )
        return redirect(url_for("game", data=encode_state(state)))

    pitch_html = render_pitch(state, event.get("category", ""), event.get("description", ""))

    body = f"""
<h2>比赛进行中</h2>
{render_status(state)}
{pitch_html}
{feedback_html}
<div class='card'>
    <p><strong>事件类别：</strong>{event['category']}</p>
    <p><strong>场上事件：</strong>{event['description']}</p>
</div>
"""

    for option in event["options"]:
        new_state = copy.deepcopy(state)
        anger_delta = roll_range(option["anger_change"])
        debuff = get_debuff(state)
        anger_delta += debuff
        apply_anger_change(new_state, anger_delta)
        advance_time(new_state)
        debuff_note = f"（含爆发buff +{debuff}）" if debuff > 0 else ""
        new_state["last_feedback"] = (
            f"你选择了\"{option['text']}\"。怒气值{format_signed(anger_delta)}{debuff_note}，"
            f"比赛时间来到{new_state['time']}分钟。"
        )
        link = url_for("game", data=encode_state(new_state))
        body += f"<a class='choice' href='{link}'>{option['text']}</a>"

    body += render_share_box(request.url)
    return render_page("比赛进行中", body)


# ========================
# 启动
# ========================

if __name__ == "__main__":
    app.run(debug=True)