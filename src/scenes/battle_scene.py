import pygame as pg
import random
from typing import override

from src.scenes.scene import Scene
from src.utils import GameSettings, Logger
from src.utils.definition import Element, ELEMENT_CHART
from src.interface.components.button import Button
from src.core.services import scene_manager, resource_manager, sound_manager
from src.core import GameManager

# [New] 野生寶可夢池 (隨機出現用)
WILD_POOL = [
    {"name": "Wild Charmander", "element": "Fire", "sprite_path": "menu_sprites/menusprite2.png"},
    {"name": "Wild Squirtle",   "element": "Water", "sprite_path": "menu_sprites/menusprite3.png"},
    {"name": "Wild Bulbasaur",  "element": "Grass", "sprite_path": "menu_sprites/menusprite4.png"},
    {"name": "Wild Gengar",     "element": "Normal", "sprite_path": "menu_sprites/menusprite5.png"},
]

class BattleScene(Scene):
    def __init__(self) -> None:
        super().__init__()
        self.font = pg.font.SysFont(None, 30)
        self.font_small = pg.font.SysFont(None, 24)
        # [New] 復活特效計時器
        self.revive_timer = 0.0
        # [New] 載入背景圖 (如果沒有圖，程式會用 fallback 顏色)
        try:
            self.bg_img = resource_manager.get_image("backgrounds/background1.png")
            self.bg_img = pg.transform.scale(self.bg_img, (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))
        except:
            self.bg_img = None

        # [New] 進場動畫變數
        self.anim_offset_player = -500 # 玩家從左邊外面滑進來
        self.anim_offset_enemy = 500   # 敵人從右邊外面滑進來
        self.anim_finished = False
        self.game_manager: GameManager | None = None
        
        self.player_mon: dict = {}
        self.enemy_mon: dict = {}
        self.battle_msg: str = ""
        self.player_shake = 0.0 
        self.enemy_shake = 0.0  
        self.is_bush_battle = False # 用來判斷是否可以捕捉

        # --- UI 按鈕 (主選單) ---
        btn_y = GameSettings.SCREEN_HEIGHT - 100
        btn_w, btn_h = 80, 80 # 正方形
        gap = 20
        start_x = 500
        
        # 1. 攻擊按鈕
        self.btn_attack = Button("UI/button_play.png", "UI/button_play_hover.png", 
                                 start_x, btn_y, btn_w, btn_h, self.on_click_attack)
        
        # 2. 背包按鈕
        self.btn_bag = Button("UI/button_backpack.png", "UI/button_backpack_hover.png", 
                              start_x + (btn_w+gap)*1, btn_y, btn_w, btn_h, self.on_click_bag)
        
        # 3. 換人按鈕
        self.btn_switch = Button("UI/button_setting.png", "UI/button_setting_hover.png", 
                                 start_x + (btn_w+gap)*2, btn_y, btn_w, btn_h, self.on_click_switch)

        # 4. 逃跑按鈕
        self.btn_run = Button("UI/button_x.png", "UI/button_x_hover.png", 
                              start_x + (btn_w+gap)*3, btn_y, btn_w, btn_h, self.on_click_run)

        # 返回按鈕
        self.btn_back = Button("UI/button_back.png", "UI/button_back_hover.png",
                               0, 0, 50, 50, self.on_click_back)
        
        # [New] 戰鬥結束後的離開按鈕 (顯示在畫面中間偏下)
        self.btn_exit = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            GameSettings.SCREEN_WIDTH // 2 - 50, GameSettings.SCREEN_HEIGHT - 250, 
            100, 100, 
            self.exit_battle
        )

        # 動態生成的按鈕列表
        self.item_buttons: list[Button] = []
        self.pokemon_buttons: list[Button] = [] 
        self.current_bag_items: list[dict] = []

    @override
    def enter(self) -> None:
        """ 初始化戰鬥 """
        self.game_manager = GameManager.load("saves/game0.json")
        self.buffs = {"atk": 1.0, "def": 1.0}
        self.state = "PLAYER_TURN"
        self.item_buttons = []
        self.pokemon_buttons = []
        self.player_shake = 0.0
        self.enemy_shake = 0.0
        # [Modified] 加大初始偏移量，因為我們要讓角色站得更開
        self.anim_offset_player = -800 # 從更左邊出來
        self.anim_offset_enemy = 800   # 從更右邊出來
        self.anim_finished = False
        
        # 1. 判斷戰鬥類型 (是否為草叢戰鬥)
        # GameScene 裡如果有按 B 鍵觸發，會設定這個 Flag
        if hasattr(GameSettings, "IS_BUSH_BATTLE") and GameSettings.IS_BUSH_BATTLE:
            self.is_bush_battle = True
            GameSettings.IS_BUSH_BATTLE = False # 重置旗標
            self.battle_msg = "Wild Pokemon! (Win to Catch)"
        else:
            self.is_bush_battle = False # NPC 或 PVP
            self.battle_msg = "Battle Start!"

        # 2. 載入我方怪獸
        if self.game_manager and self.game_manager.bag._monsters_data:
            alive_mon = next((m for m in self.game_manager.bag._monsters_data if m.get("hp", 0) > 0), None)
            if alive_mon:
                self.player_mon = alive_mon
            else:
                self.player_mon = self.game_manager.bag._monsters_data[0]
                self.battle_msg = "Your pokemon is fainted..."
        else:
            self.player_mon = self._create_temp_mon("Pikachu", "Normal")

        # 3. 載入敵方怪獸 (PVP 或 隨機)
        if hasattr(GameSettings, "PVP_ENEMY_DATA") and GameSettings.PVP_ENEMY_DATA:
            # PVP 模式
            self.enemy_mon = GameSettings.PVP_ENEMY_DATA.copy()
            GameSettings.PVP_ENEMY_DATA = None
            self.battle_msg = f"PVP vs {self.enemy_mon.get('name')}!"
            self.is_bush_battle = False # PVP 絕對不能抓
        else:
            # 隨機遭遇 (包含 NPC 和 草叢)
            self._create_random_wild_mon()

        self.enemy_mon["hp"] = self.enemy_mon.get("max_hp", 100)

    def _create_random_wild_mon(self):
        base_lvl = self.player_mon.get("level", 5)
        wild_lvl = max(1, base_lvl + random.randint(-2, 2))
        template = random.choice(WILD_POOL)
        
        self.enemy_mon = {
            "name": template["name"],
            "element": template["element"],
            "sprite_path": template["sprite_path"],
            "level": wild_lvl,
            "max_hp": 30 + wild_lvl * 10,
            "hp": 30 + wild_lvl * 10,
            "attack": 10 + wild_lvl * 2,
            "defense": 5 + wild_lvl * 1,
            "exp": 0
        }

    def _create_temp_mon(self, name, elem, hp=100, atk=20) -> dict:
        return {
            "name": name, "hp": hp, "max_hp": hp, "level": 5,
            "element": elem, "attack": atk, "defense": 5, "exp": 0,
            "sprite_path": "menu_sprites/menusprite1.png"
        }

    # ================= 戰鬥邏輯 =================

    def calculate_damage(self, attacker: dict, defender: dict, is_player_attacking: bool) -> int:
        atk_stat = attacker.get("attack", 10)
        def_stat = defender.get("defense", 10)
        
        atk_elem_str = attacker.get("element", "Normal")
        def_elem_str = defender.get("element", "Normal")

        try: atk_elem = Element(atk_elem_str)
        except: atk_elem = Element.NORMAL
        try: def_elem = Element(def_elem_str)
        except: def_elem = Element.NORMAL

        multiplier = 1.0
        if atk_elem in ELEMENT_CHART and def_elem in ELEMENT_CHART[atk_elem]:
            multiplier = ELEMENT_CHART[atk_elem][def_elem]

        if multiplier > 1.0: self.battle_msg = "Super Effective!"
        elif multiplier < 1.0: self.battle_msg = "Not very effective..."
        else: self.battle_msg = "Attacked!"

        if is_player_attacking: atk_stat *= self.buffs["atk"]
        else: def_stat *= self.buffs["def"]

        damage = int((atk_stat * multiplier) - (def_stat * 0.5))
        return max(1, damage)

    # --- 按鈕事件 ---

    def on_click_attack(self):
        if self.state != "PLAYER_TURN": return
        if self.player_mon.get("hp", 0) <= 0:
            self.battle_msg = "Your pokemon has fainted!"
            return
            
        dmg = self.calculate_damage(self.player_mon, self.enemy_mon, True)
        self.enemy_mon["hp"] -= dmg
        self.battle_msg += f" (-{dmg})"
        self.enemy_shake = 0.5
        
        if self.enemy_mon["hp"] <= 0:
            self.enemy_mon["hp"] = 0
            self.win_battle()
        else:
            self.state = "ENEMY_TURN"

    def on_click_bag(self):
        if self.state != "PLAYER_TURN": return
        self.state = "BAG_MENU"
        self._refresh_item_buttons()
        
    def on_click_switch(self):
        if self.state != "PLAYER_TURN": return
        self.state = "POKEMON_MENU"
        self._refresh_pokemon_buttons()

    def on_click_run(self):
        self.state = "LOSE"
        self.battle_msg = "You ran away..."

    def on_click_back(self):
        self.state = "PLAYER_TURN"

    def enemy_turn(self):
        pg.time.delay(500)
        dmg = self.calculate_damage(self.enemy_mon, self.player_mon, False)
        self.player_mon["hp"] -= dmg
        self.battle_msg = f"Enemy hit you! (-{dmg})"
        self.player_shake = 0.5
        
        if self.player_mon["hp"] <= 0:
            # 1. 檢查是否有守護小精靈
            # (使用 getattr 避免如果 GameManager 沒存這個變數會報錯)
            if getattr(self.game_manager, "has_fairy", False):
                # 2. 消耗小精靈
                self.game_manager.has_fairy = False
                
                # 3. [Fix] 修正變數名稱與字典寫法
                max_hp = self.player_mon.get("max_hp", 100)
                self.player_mon["hp"] = int(max_hp * 0.5) # 回血 50%
                
                # 4. 設定特效與訊息
                self.battle_msg = "Guardian Fairy sacrificed to revive you!"
                self.revive_timer = 2.0 # 觸發 draw 裡面的特效，顯示 2 秒
                
                # 5. 強制結束敵人回合，輪回玩家
                self.state = "PLAYER_TURN"
                
            else:
                # === 原本的死亡邏輯 ===
                self.player_mon["hp"] = 0
                self.battle_msg = f"{self.player_mon['name']} fainted!"
                alive = [m for m in self.game_manager.bag._monsters_data if m.get("hp",0) > 0]
                if alive:
                    self.state = "POKEMON_MENU"
                    self._refresh_pokemon_buttons()
                else:
                    self.state = "LOSE"
    # ================= 道具與換人 =================

    def _refresh_item_buttons(self):
        self.item_buttons = []
        bag_items = self.game_manager.bag._items_data
        self.current_bag_items = [it for it in bag_items if it.get("effect_type", "NONE") != "NONE"]
        
        start_x, start_y = 220, GameSettings.SCREEN_HEIGHT - 200
        for i, item in enumerate(self.current_bag_items):
            btn = Button("UI/button_save.png", "UI/button_save_hover.png",
                         start_x, start_y - i * 70, 60, 60, 
                         lambda it=item: self.use_item(it))
            self.item_buttons.append(btn)

    def _refresh_pokemon_buttons(self):
        self.pokemon_buttons = []
        monsters = self.game_manager.bag._monsters_data
        start_x, start_y = 400, GameSettings.SCREEN_HEIGHT-400
        for i, mon in enumerate(monsters):
            if mon.get("hp", 0) > 0:
                btn = Button("UI/button_play.png", "UI/button_play_hover.png",
                             start_x, start_y + i * 70, 60, 60,
                             lambda m=mon: self.perform_switch(m))
                self.pokemon_buttons.append(btn)

    def use_item(self, item: dict):
        effect = item.get("effect_type")
        val = item.get("value", 0)
        
        if effect == "HEAL":
            self.player_mon["hp"] = min(self.player_mon["max_hp"], self.player_mon["hp"] + val)
            self.battle_msg = f"Healed +{val}"
        elif effect == "ATK_UP":
            self.buffs["atk"] += 0.5
            self.battle_msg = "Attack Up!"
        elif effect == "DEF_UP":
            self.buffs["def"] += 0.5
            self.battle_msg = "Defense Up!"
            
        item["count"] -= 1
        if item["count"] <= 0:
            self.game_manager.bag._items_data.remove(item)
            
        self.state = "ENEMY_TURN"

    def perform_switch(self, new_mon: dict):
        if new_mon == self.player_mon:
            self.battle_msg = "Already in battle!"
            return
        self.player_mon = new_mon
        self.battle_msg = f"Go! {new_mon['name']}!"
        self.state = "ENEMY_TURN"
        self.buffs = {"atk": 1.0, "def": 1.0}

    # ================= 勝利結算 (任務與捕捉) =================

    def win_battle(self):
        self.state = "WIN"
        self.battle_msg = "You Won!"
        
        # 1. [New] 任務計數與獎勵 (Quest Logic)
        # 安全存取 quest 屬性，避免沒存檔報錯
        quest = getattr(self.game_manager, "quest", None)
        if quest and not quest.get("is_completed", False):
            # 任務進度 +1
            quest["current_count"] = quest.get("current_count", 0) + 1
            
            # 檢查是否達成
            if quest["current_count"] >= quest["target_count"]:
                quest["current_count"] = quest["target_count"]
                quest["is_completed"] = True
                
                # 給予獎勵
                reward = quest.get("reward_coins", 100)
                self.battle_msg += f" Quest Complete! +${reward}"
                
                # 加錢到背包
                bag = self.game_manager.bag
                coins = next((x for x in bag._items_data if x["name"] == "Coins"), None)
                if coins:
                    coins["count"] += reward
                else:
                    bag._items_data.append({"name": "Coins", "count": reward, "sprite_path": "ingame_ui/coin.png"})
            else:
                # 顯示目前進度
                self.battle_msg += f" (Quest: {quest['current_count']}/{quest['target_count']})"

        # 2. 經驗值與升級 (Experience Logic)
        if self.player_mon["hp"] > 0:
            self.player_mon["exp"] = self.player_mon.get("exp", 0) + 50
            if "Quest" not in self.battle_msg: self.battle_msg += " +50 EXP" # 避免訊息太長
            
            if self.player_mon["exp"] >= 100:
                self.player_mon["exp"] -= 100
                self.player_mon["level"] += 1
                self.player_mon["max_hp"] += 10
                self.player_mon["attack"] += 5
                self.player_mon["defense"] += 5
                self.player_mon["hp"] = self.player_mon["max_hp"]
                self.battle_msg = "Level Up! " + self.battle_msg
                self.check_evolution()

        # 3. [New] 捕捉機制 (Capture Logic)
        # 只有在「草叢戰鬥 (is_bush_battle)」時才捕捉
        if self.is_bush_battle:
            caught_mon = self.enemy_mon.copy()
            caught_mon["hp"] = caught_mon["max_hp"] # 補滿血
            self.game_manager.bag._monsters_data.append(caught_mon)
            self.battle_msg = f"Caught {caught_mon['name']}!" # 覆蓋訊息顯示捕捉

        # 儲存所有變更 (任務進度、金錢、經驗、新怪獸)
        self.game_manager.save("saves/game0.json")

    def check_evolution(self):
        evo_lvl = self.player_mon.get("next_evo_level", 0)
        evo_sprite = self.player_mon.get("next_evo_sprite", "")
        if evo_lvl > 0 and self.player_mon["level"] >= evo_lvl and evo_sprite:
            self.player_mon["sprite_path"] = evo_sprite
            self.player_mon["name"] = f"Mega {self.player_mon['name']}"
            self.player_mon["next_evo_level"] = 0
            self.battle_msg = "Evolved!"

    def exit_battle(self):
        scene_manager.change_scene("game")

    # ================= Update / Draw =================

    @override
    def update(self, dt: float) -> None:
        # [New] 處理進場動畫 (Lerp 效果)
        if not self.anim_finished:
            # 讓偏移量慢慢歸零 (0.1 是平滑係數)
            self.anim_offset_player += (0 - self.anim_offset_player) * 0.05
            self.anim_offset_enemy += (0 - self.anim_offset_enemy) * 0.05
            
            # 當兩者都很接近 0 時，視為動畫結束
            if abs(self.anim_offset_player) < 1 and abs(self.anim_offset_enemy) < 1:
                self.anim_offset_player = 0
                self.anim_offset_enemy = 0
                self.anim_finished = True

        if self.state == "PLAYER_TURN":
            self.btn_attack.update(dt)
            self.btn_bag.update(dt)
            self.btn_switch.update(dt)
            self.btn_run.update(dt)
        if self.player_shake > 0: self.player_shake -= dt
        if self.enemy_shake > 0: self.enemy_shake -= dt
            
        elif self.state == "BAG_MENU":
            self.btn_back.update(dt)
            for btn in self.item_buttons: btn.update(dt)
            
        elif self.state == "POKEMON_MENU":
            self.btn_back.update(dt)
            for btn in self.pokemon_buttons: btn.update(dt)
                
        elif self.state == "ENEMY_TURN":
            self.enemy_turn()
            
        elif self.state in ("WIN", "LOSE"):
            # [New] 讓按鈕可以被點擊
            self.btn_exit.update(dt)
            
            # 保留原本的空白鍵功能 (二選一都可以)
            if pg.key.get_pressed()[pg.K_SPACE]:
                self.exit_battle()

    @override
    def draw(self, screen: pg.Surface) -> None:
        screen.fill((220, 220, 255))
        # 1. [Modified] 繪製背景
        if self.bg_img:
            screen.blit(self.bg_img, (0, 0))
        else:
            # 如果沒圖，改用漸層色或比較好看的顏色
            screen.fill((240, 248, 255)) # AliceBlue
            
        # 2. 繪製寶可夢 (帶入動畫偏移量)
        # 注意：這裡把 anim_offset 傳進去
        self.draw_mon_info(screen, 150 + self.anim_offset_player, 250, self.player_mon, True)
        self.draw_mon_info(screen, 700 + self.anim_offset_enemy, 50, self.enemy_mon, False)

        # 訊息框
        pg.draw.rect(screen, (255, 255, 255), (0, GameSettings.SCREEN_HEIGHT-150, GameSettings.SCREEN_WIDTH, 150))
        pg.draw.line(screen, (0,0,0), (0, GameSettings.SCREEN_HEIGHT-150), (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT-150), 3)
        msg_surf = self.font.render(self.battle_msg, True, (0, 0, 0))
        screen.blit(msg_surf, (50, GameSettings.SCREEN_HEIGHT - 100))

        if self.state == "PLAYER_TURN":
            self.btn_attack.draw(screen)
            self.btn_bag.draw(screen)
            self.btn_switch.draw(screen)
            self.btn_run.draw(screen)
            off_x, off_y = 10, 30
            screen.blit(self.font_small.render("Attack", True, (0,0,0)), (self.btn_attack.hitbox.x+off_x, self.btn_attack.hitbox.y+off_y))
            screen.blit(self.font_small.render("Bag", True, (0,0,0)), (self.btn_bag.hitbox.x+off_x+10, self.btn_bag.hitbox.y+off_y))
            screen.blit(self.font_small.render("Poke", True, (0,0,0)), (self.btn_switch.hitbox.x+off_x+10, self.btn_switch.hitbox.y+off_y))
            screen.blit(self.font_small.render("Run", True, (0,0,0)), (self.btn_run.hitbox.x+off_x+10, self.btn_run.hitbox.y+off_y))

        elif self.state == "BAG_MENU":
            menu_bg = pg.Rect(200, GameSettings.SCREEN_HEIGHT - 450, 350, 350)
            pg.draw.rect(screen, (240, 240, 240), menu_bg)
            pg.draw.rect(screen, (0, 0, 0), menu_bg, 2)
            screen.blit(self.font.render("Select Item", True, (0,0,0)), (menu_bg.x+20, menu_bg.y+20))
            self.btn_back.hitbox.x = menu_bg.right - 60
            self.btn_back.hitbox.y = menu_bg.top + 10
            self.btn_back.draw(screen)

            for i, btn in enumerate(self.item_buttons):
                btn.draw(screen)
                if i < len(self.current_bag_items):
                    item = self.current_bag_items[i]
                    name = item.get("name", "Unknown")
                    count = item.get("count", 0)
                    path = item.get("sprite_path", "")
                    if path:
                        try:
                            img = resource_manager.get_image(path)
                            img = pg.transform.scale(img, (40, 40))
                            screen.blit(img, (btn.hitbox.x + 10, btn.hitbox.y + 10))
                        except: pass
                    txt = self.font_small.render(f"{name} x{count}", True, (0, 0, 0))
                    screen.blit(txt, (btn.hitbox.right + 15, btn.hitbox.centery - 10))

        elif self.state == "POKEMON_MENU":
            menu_bg = pg.Rect(380, GameSettings.SCREEN_HEIGHT - 450, 350, 350)
            pg.draw.rect(screen, (240, 240, 240), menu_bg)
            pg.draw.rect(screen, (0,0,0), menu_bg, 2)
            screen.blit(self.font.render("Switch Pokemon", True, (0,0,0)), (menu_bg.x+20, menu_bg.y+20))
            self.btn_back.hitbox.x = menu_bg.right - 60
            self.btn_back.hitbox.y = menu_bg.top + 10
            self.btn_back.draw(screen)
            
            live_monsters = [m for m in self.game_manager.bag._monsters_data if m.get("hp", 0) > 0]
            for i, btn in enumerate(self.pokemon_buttons):
                btn.draw(screen)
                if i < len(live_monsters):
                    mon = live_monsters[i]
                    path = mon.get("sprite_path", "")
                    if path:
                        try:
                            img = resource_manager.get_image(path)
                            img = pg.transform.scale(img, (40, 40))
                            icon_x = btn.hitbox.centerx - 20
                            icon_y = btn.hitbox.centery - 20
                            screen.blit(img, (icon_x, icon_y))
                        except: pass
                    name = mon.get("name", "???")
                    hp = mon.get("hp", 0)
                    max_hp = mon.get("max_hp", 0)
                    lvl = mon.get("level", 1)
                    elem = mon.get("element", "Normal")
                    info_text = f"{name} Lv.{lvl} ({elem}) {hp}/{max_hp}"
                    text_color = (0, 0, 0)
                    if elem == "Fire": text_color = (200, 0, 0)
                    elif elem == "Water": text_color = (0, 0, 200)
                    elif elem == "Grass": text_color = (0, 150, 0)
                    txt = self.font_small.render(info_text, True, text_color)
                    screen.blit(txt, (btn.hitbox.right + 15, btn.hitbox.centery - 10))

        
        # [New] 戰鬥結束時顯示返回按鈕
        if self.state in ("WIN", "LOSE"):
            self.btn_exit.draw(screen)
            # 補個文字提示
            txt = self.font.render("Return", True, (0, 0, 0))
            screen.blit(txt, (self.btn_exit.hitbox.centerx - txt.get_width() // 2, self.btn_exit.hitbox.bottom + 10))

        # 如果正在復活，畫一個閃光或文字
        # 這需要你在 update 裡觸發復活時，設一個 timer (例如 self.revive_timer = 1.0)
        if hasattr(self, 'revive_timer') and self.revive_timer > 0:
            self.revive_timer -= 0.016 # 假設 60fps
            
            # 畫出青色大字
            font = pg.font.SysFont(None, 80)
            text = font.render("REVIVED!", True, (0, 255, 255))
            # 加上黑色描邊
            outline = font.render("REVIVED!", True, (0, 0, 0))
            
            center_x = screen.get_width() // 2 - text.get_width() // 2
            center_y = screen.get_height() // 2 - text.get_height() // 2
            
            screen.blit(outline, (center_x + 2, center_y + 2))
            screen.blit(text, (center_x, center_y))
    def draw_mon_info(self, screen, x, y, mon, is_player):
        # 資料準備
        name = str(mon.get("name", "Unknown"))
        hp = int(mon.get("hp", 0))
        max_hp = int(mon.get("max_hp", 100))
        lvl = int(mon.get("level", 1))
        elem = str(mon.get("element", "Normal"))
        path = str(mon.get("sprite_path", ""))
        
        # 計算數值
        base_atk = int(mon.get("attack", 0))
        base_def = int(mon.get("defense", 0))
        if is_player:
            final_atk = int(base_atk * self.buffs.get("atk", 1.0))
            final_def = int(base_def * self.buffs.get("def", 1.0))
        else:
            final_atk, final_def = base_atk, base_def

        # [Modified] 設定變大的尺寸
        IMG_SIZE = 280  # 變大！(原本是 150)
        
        # 1. 繪製底座陰影 (配合大圖調整位置與大小)
        shadow_w, shadow_h = 180, 50
        shadow_x = x + (IMG_SIZE - shadow_w) // 2
        shadow_y = y + IMG_SIZE - 20
        
        shape_surf = pg.Surface((shadow_w, shadow_h), pg.SRCALPHA)
        pg.draw.ellipse(shape_surf, (0, 0, 0, 80), (0, 0, shadow_w, shadow_h))
        screen.blit(shape_surf, (shadow_x, shadow_y))

        # 2. 繪製怪獸圖片 (放大版)
        offset_x, offset_y = 0, 0
        # (保留震動邏輯)
        if is_player and self.player_shake > 0:
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
        elif not is_player and self.enemy_shake > 0:
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)

        try:
            img = resource_manager.get_image(path)
            # [Modified] 這裡改成新的大尺寸
            img = pg.transform.scale(img, (IMG_SIZE, IMG_SIZE))
            if is_player: img = pg.transform.flip(img, True, False)
            screen.blit(img, (x + offset_x, y + offset_y))
        except:
            pg.draw.rect(screen, (100,100,100), (x, y, IMG_SIZE, IMG_SIZE))

        # ===========================
        # 4. 繪製 HUD 資訊面板 (Info Box)
        # ===========================
        hud_w, hud_h = 240, 110
        
        # [Modified] 調整面板位置：貼緊螢幕邊緣，不要擋住中間
        if is_player:
            # 玩家 (左下角)：HUD 放在圖片的「上方」且靠左
            # x 是圖片位置 (約100)，我們讓 HUD 貼齊螢幕左邊緣 (20)
            hud_x = 20 
            hud_y = y - hud_h + 20 # 放在頭頂上方
        else:
            # 敵人 (右上角)：HUD 放在圖片的「下方」且靠右
            # 讓 HUD 貼齊螢幕右邊緣
            hud_x = GameSettings.SCREEN_WIDTH - hud_w - 20
            hud_y = y + 280 - 30 # 放在腳下 (280 是圖片大小)
            
        # 畫白底圓角框
        pg.draw.rect(screen, (255, 255, 255, 230), (hud_x, hud_y, hud_w, hud_h), border_radius=10)
        # 畫深色邊框
        pg.draw.rect(screen, (60, 60, 60), (hud_x, hud_y, hud_w, hud_h), 3, border_radius=10)

        # 文字資訊
        screen.blit(self.font_small.render(f"{name}", True, (0, 0, 0)), (hud_x + 15, hud_y + 10))
        screen.blit(self.font_small.render(f"Lv.{lvl} ({elem})", True, (80, 80, 80)), (hud_x + 15, hud_y + 35))

        # 4. 血條
        bar_x = hud_x + 15
        bar_y = hud_y + 60
        bar_w = 210
        bar_h = 14
        
        pg.draw.rect(screen, (200, 200, 200), (bar_x, bar_y, bar_w, bar_h), border_radius=7)
        ratio = max(0, min(1, hp / max_hp))
        
        if ratio > 0.5: hp_color = (40, 220, 40)
        elif ratio > 0.2: hp_color = (255, 200, 0)
        else: hp_color = (220, 40, 40)
            
        pg.draw.rect(screen, hp_color, (bar_x, bar_y, bar_w * ratio, bar_h), border_radius=7)
        
        # 血量數字
        hp_str = f"{hp}/{max_hp}"
        hp_surf = self.font_small.render(hp_str, True, (50, 50, 50))
        screen.blit(hp_surf, (bar_x + bar_w - hp_surf.get_width(), bar_y + 20))

        # 5. 攻防數值
        stats_text = f"ATK:{final_atk} DEF:{final_def}"
        text_color = (100, 100, 100)
        if is_player and (self.buffs["atk"] > 1.0 or self.buffs["def"] > 1.0):
            text_color = (0, 100, 255)
        screen.blit(self.font_small.render(stats_text, True, text_color), (bar_x, bar_y + 20))

        # 6. 經驗條 (僅玩家)
        if is_player:
            exp = int(mon.get("exp", 0))
            exp_bar_w = hud_w
            # 畫在 HUD 最下方邊緣
            pg.draw.rect(screen, (200, 200, 255), (hud_x, hud_y + hud_h - 4, exp_bar_w, 4))
            pg.draw.rect(screen, (0, 0, 200), (hud_x, hud_y + hud_h - 4, exp_bar_w * (exp/100), 4))