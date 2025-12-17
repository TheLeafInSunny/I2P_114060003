import pygame as pg
import threading
import time
import math
import requests 

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.sprites import Sprite, Animation
from typing import override

##[myself]
from src.interface.components.button import Button
from src.core.services import sound_manager, input_manager, scene_manager, resource_manager
from src.interface.components.chat_overlay import ChatOverlay


class VolumeSlider:
    def __init__(self, x: int, y: int, width: int,
                 min_value: float, max_value: float, value: float,
                 on_change=None):
        self.x = x
        self.y = y
        self.width = width
        self.min_value = min_value
        self.max_value = max_value
        self.value = value      # 0 ~ 100
        self.on_change = on_change

        self.rect = pg.Rect(x, y - 8, width, 16)
        self.font = pg.font.SysFont(None, 20)

    def _value_to_x(self) -> int:
        t = (self.value - self.min_value) / (self.max_value - self.min_value)
        return int(self.x + t * self.width)

    def _x_to_value(self, px: int) -> float:
        t = (px - self.x) / self.width
        t = max(0.0, min(1.0, t))
        return self.min_value + t * (self.max_value - self.min_value)

    def update(self, dt: float) -> None:
        if input_manager.mouse_pressed(1) and self.rect.collidepoint(input_manager.mouse_pos):
            new_value = self._x_to_value(input_manager.mouse_pos[0])
            self.value = new_value
            if self.on_change is not None:
                self.on_change(self.value)

    def draw(self, screen: pg.Surface) -> None:
        center_y = self.y
        # 底線
        pg.draw.line(screen, (200, 200, 200), (self.x, center_y), (self.x + self.width, center_y), 4)
        # 滑塊
        knob_x = self._value_to_x()
        knob_rect = pg.Rect(0, 0, 14, 24)
        knob_rect.center = (knob_x, center_y)
        pg.draw.rect(screen, (255, 255, 255), knob_rect)
        # 顯示數值
        txt = self.font.render(f"Volume: {int(self.value)}", True, (0, 0, 0))
        screen.blit(txt, (self.x, center_y - 30))
##

class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite
    
    def __init__(self):
        self.chat_history = []
        # ===== [New] 對話框系統 (Dialogue System) =====
        self.is_dialogue_open = False
        self.dialogue_rect = pg.Rect(240, 450, 800, 200) # 下方的長條對話框
        self.pending_quest_data = {} # 暫存「等待玩家同意」的任務資料


        # 守護小精靈設定
        self.fairy_pos = [0, 0] # 小精靈現在的位置
        self.fairy_history = [] # 記錄玩家走過的路徑 (用來做延遲跟隨)
        self.fairy_angle = 0.0  # 用來做呼吸燈動畫
        self.fairy_pos = [0, 0] 
        # ... (原本的其他變數)
    
        
        # 接受按鈕 (Yes)
        self.btn_dialogue_yes = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            self.dialogue_rect.right - 180, self.dialogue_rect.bottom - 80, 60, 60,
            self.accept_pending_quest
        )
        
        # 拒絕按鈕 (No)
        self.btn_dialogue_no = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            self.dialogue_rect.right - 100, self.dialogue_rect.bottom - 80, 60, 60,
            self.close_dialogue
        )
        self.particles = []
        super().__init__()
        # 顯示背包內容用的字型
        self.font_small = pg.font.SysFont(None, 20)
        self.font_quest = pg.font.SysFont(None, 30)
        # [New] 畫面提示系統 (Notification)
        self.notif_text = ""
        self.notif_timer = 0.0
        # Game Manager
        manager = GameManager.load("saves/game0.json")
        if manager is None:
            Logger.error("Failed to load game manager")
            exit(1)
        self.game_manager = manager

        # ... (原本的 nav_places 定義) ...
        
        # [New] Quest UI 初始化
        self.is_quest_open = False
        self.quest_rect = pg.Rect(300, 150, 600, 400) # 任務視窗大小
        
        # 任務按鈕 (放在導航按鈕下面)
        self.btn_quest = Button(
            "UI/button_save.png", "UI/button_save_hover.png", 
            20, 310, 60, 60, # 假設 Nav 在 240, 這個放在 310
            self.open_quest
        )
        
        # 任務視窗的關閉鈕
        self.btn_quest_close = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            self.quest_rect.right - 60, self.quest_rect.top + 20,
            50, 50, 
            self.close_quest
        )
        # [New] 任務視窗開關
        
        # Online Manager
        if GameSettings.IS_ONLINE:
            self.online_manager = OnlineManager()
        else:
            self.online_manager = None
        self.online_animations = {}#[mine]

            # ===== [New] Minimap (小地圖) =====
        self.minimap_size_w = 200  # 小地圖固定寬度
        self.minimap_margin = 20   # 距離左上角的距離
        self.minimap_surface = None # 用來存「縮小版地圖」的快取
        self.minimap_rect = None    # 小地圖在螢幕上的位置
        self.minimap_cache_map_name = "" # 記住現在是哪張圖，換圖時要重算
        
        # 戰鬥狀態: PLAYER_TURN, ENEMY_TURN, BAG_MENU, POKEMON_MENU, WIN, LOSE
        self.state: str = "PLAYER_TURN"
        self.buffs = {"atk": 1.0, "def": 1.0}
##
        # ===== Overlay 狀態與按鈕 =====
        self.is_overlay_open = False

##[mine]        
        # ===== Shop Overlay =====
        self.is_shop_open = False
        self.shop_rect = pg.Rect(200, 100, 880, 520) # 商店視窗大小
        
        # 商店模式與動態按鈕列表
        self.shop_mode = "BUY"  # 預設是買東西
        self.shop_dynamic_buttons = [] # 用來存「現在該顯示的商品按鈕」

        # 分頁按鈕 (Buy / Sell)
        self.btn_tab_buy = Button("UI/button_back.png", "UI/button_back_hover.png", 
                                  self.shop_rect.x + 700, self.shop_rect.top + 400, 60, 60, 
                                  lambda: self.set_shop_mode("BUY"))
        
        self.btn_tab_sell = Button("UI/button_play.png", "UI/button_play_hover.png", 
                                   self.shop_rect.x +780, self.shop_rect.top + 400, 60, 60, 
                                   lambda: self.set_shop_mode("SELL"))
        
        # 商店的返回按鈕
        self.button_shop_close = Button(
            img_path="UI/button_x.png",
            img_hovered_path="UI/button_x_hover.png",
            x=self.shop_rect.right - 80,
            y=self.shop_rect.top + 20,
            width=60,
            height=60,
            on_click=self.close_shop
        )
        
        # 預設商品 (名稱, 價格, 圖片路徑)
        self.shop_items = [
            # [修改] 加上 effect_type 和 value
            {"name": "Potion", "price": 50, "sprite_path": "ingame_ui/potion.png", "effect_type": "HEAL", "value": 150},
            
            {"name": "Pokeball", "price": 200, "sprite_path": "ingame_ui/ball.png", "effect_type": "NONE", "value": 0},
            {"name": "Strength Potion", "price": 100, "sprite_path": "ingame_ui/potion.png", "effect_type": "ATK_UP", "value": 10},
            {"name": "Defense Potion", "price": 100, "sprite_path": "ingame_ui/potion.png", "effect_type": "DEF_UP", "value": 10},
            {"name": "Guardian Fairy", "price": 300, "sprite_path": "ingame_ui/star.png", "effect_type": "REVIVE", "value": 1}
        ]
        # 在 __init__ 裡面找到這段並覆蓋
        self.shop_items = [
            {"name": "Potion", "price": 50, "sprite_path": "ingame_ui/potion.png", "effect_type": "HEAL", "value": 150,
             "desc": "Restores 150 HP. Essential for adventure."},
            
            {"name": "Pokeball", "price": 200, "sprite_path": "ingame_ui/ball.png", "effect_type": "NONE", "value": 0,
             "desc": "A tool for catching wild Pokemon."},
            
            {"name": "Strength Potion", "price": 100, "sprite_path": "ingame_ui/potion.png", "effect_type": "ATK_UP", "value": 10,
             "desc": "Increases Attack power temporarily."},
            
            {"name": "Defense Potion", "price": 100, "sprite_path": "ingame_ui/potion.png", "effect_type": "DEF_UP", "value": 10,
             "desc": "Increases Defense power temporarily."},
            
            {"name": "Guardian Fairy", "price": 300, "sprite_path": "ingame_ui/star.png", "effect_type": "REVIVE", "value": 1,
             "desc": "Revives you once when you faint. Very rare!"}
        ]
        self.refresh_shop_buttons()
        # [mine] 導航系統初始化
        self.is_nav_open = False
        self.nav_buttons = []
        # 定義導航地點 (座標要對應 map.tmx 的邏輯位置)
        self.nav_places = [
            {"name": "Shop", "x": 55, "y": 13},
            {"name": "Gym", "x": 24, "y": 23},
            {"name": "Garden", "x": 16, "y": 28},
            {"name": "Home", "x": 16, "y": 30}
        ]
        
        # 導航開關按鈕 (放在左邊，小地圖下方)
        self.btn_nav = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            20, 240, 60, 60, 
            self.toggle_nav
        )

        # 停止導航按鈕 (放在 NAV 按鈕左邊)
        self.btn_stop_nav = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            90, 240, 60, 60, 
            self.stop_navigation
        )
        
        # 購買按鈕清單 (動態生成)
        self.shop_buttons = []
        for i, item in enumerate(self.shop_items):
            # 這裡使用 lambda 的小技巧來綁定 item
            btn = Button(
                img_path="UI/button_shop.png",  
                img_hovered_path="UI/button_shop_hover.png",
                x=self.shop_rect.x + 350,
                y=self.shop_rect.y + 100 + i * 80,
                width=60,
                height=60,
                on_click=lambda it=item: self.buy_item(it)
            )
            self.shop_buttons.append(btn)

        
##
        # 右上角打開 overlay 的按鈕
        btn_size = GameSettings.TILE_SIZE
        self.button_overlay = Button(
            img_path="UI/button_backpack.png",
            img_hovered_path="UI/button_backpack_hover.png", 
            x=GameSettings.SCREEN_WIDTH - btn_size - 10,
            y=10,
            width=btn_size,
            height=btn_size,
            on_click=self.open_overlay #被點到時，會呼叫 self.open_overlay()
        )
        
        

        # 中央 overlay 面板區域
        panel_w, panel_h = 900, 700
        panel_x = (GameSettings.SCREEN_WIDTH - panel_w) // 2
        panel_y = (GameSettings.SCREEN_HEIGHT - panel_h) // 2
        self.overlay_rect = pg.Rect(panel_x, panel_y, panel_w, panel_h)

        # overlay 裡的返回按鈕
        self.button_back = Button(
            img_path="UI/button_back.png",    
            img_hovered_path="UI/button_back_hover.png",
            x=panel_x + panel_w // 2 - 60,
            y=panel_y + panel_h - 60,
            width=100,
            height=100,
            on_click=self.close_overlay
        )
            # ===== Setting Overlay 狀態與元件 =====
        self.is_setting_open = False
        self.audio_volume = 100.0  # 0~100

        # 啟設定 overlay 的按鈕（放在右上角，背包按鈕下面）
        self.button_setting_overlay = Button(
            img_path="UI/button_setting.png",
            img_hovered_path="UI/button_setting_hover.png",
            x=GameSettings.SCREEN_WIDTH - btn_size - 10,
            y=10 + btn_size + 10,   # 比原本 overlay 按鈕再往下
            width=btn_size,
            height=btn_size,
            on_click=self.toggle_setting_overlay
        )


        # 設定 overlay 的 panel 區域
        set_w, set_h = 450, 260
        set_x = (GameSettings.SCREEN_WIDTH - set_w) // 2
        set_y = (GameSettings.SCREEN_HEIGHT - set_h) // 2
        self.setting_rect = pg.Rect(set_x, set_y, set_w, set_h)

        #返回按鈕
        self.button_setting_back = Button(
            img_path="UI/button_x.png",
            img_hovered_path="UI/button_x_hover.png",
            x=set_x + set_w - 60 - 40,   # 靠右上角一點
            y=set_y + 20,
            width=60,
            height=40,
            on_click=self.toggle_setting_overlay   # 點了就關閉設定 overlay
        )

        # 設定 overlay 裡的音量 slider
        self.slider_volume = VolumeSlider(
            x=set_x + 40,
            y=set_y + 80,
            width=set_w - 80,
            min_value=0.0,
            max_value=100.0,
            value=self.audio_volume,
            on_change=self.on_volume_changed
        )

        # 設定 overlay 裡的 Save / Load 按鈕
        btn_w, btn_h = 100, 100
        gap = 20
        self.button_save = Button(
            img_path="UI/button_save.png",
            img_hovered_path="UI/button_save_hover.png",
            x=set_x + set_w // 2 - btn_w - gap//2,
            y=set_y + set_h - 70,
            width=btn_w,
            height=btn_h,
            on_click=self.on_click_save
        )
 
        self.button_load = Button(
            img_path="UI/button_load.png",
            img_hovered_path="UI/button_load_hover.png",
            x=set_x + set_w // 2 + gap//2,
            y=set_y + set_h - 70,
            width=btn_w,               
            height=btn_h,
            on_click=self.on_click_load  
        )

        # 設定 overlay 標題用字型（如果你之前沒有）
        self.font_small = pg.font.SysFont(None, 24)

    # [Modified] 聊天系統初始化 (WebSocket 版本)
        # 移除 import requests
        self.chat_history = [] 

        # 定義 1: 傳送訊息 Callback
        def on_send_chat(text: str) -> bool:
            if self.online_manager:
                # [Fix] 改用 OnlineManager 的 WebSocket 方法
                return self.online_manager.send_chat(text)
            return False

        # 定義 2: 獲取訊息 Callback
        def on_get_messages(limit: int) -> list[dict]:
            return self.chat_history[-limit:]

        # 初始化 Overlay
        self.chat_overlay = ChatOverlay(
            send_callback=on_send_chat,
            get_messages=on_get_messages
        )
        
        self.online_player_states = {}
     # [New] 定義關閉時的動作：清除歷史紀錄
        def on_close_chat():
            self.chat_history = [] # 清空列表
            # input_manager.clear_buffer() # 如果需要也可以清空輸入緩衝

        # [Modified] 初始化 Overlay 時傳入 on_close_callback
        self.chat_overlay = ChatOverlay(
            send_callback=on_send_chat,
            get_messages=on_get_messages,
            on_close_callback=on_close_chat # 綁定剛剛定義的函數
        )
 

    def open_quest(self):
            self.is_quest_open = True

    def close_quest(self):
        self.is_quest_open = False
    @override
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 103 Pallet Town.ogg")
        
        # [Fix] 重新讀取存檔 (Sync Data)
        # 這樣才能把 BattleScene 寫入的「新怪獸」和「任務進度」讀進來
        reloaded_gm = GameManager.load("saves/game0.json")
        if reloaded_gm:
            # 更新背包和任務資料
            self.game_manager.bag = reloaded_gm.bag
            self.game_manager.quest = reloaded_gm.quest
            
            # 同步玩家數值 (HP, EXP, Level)，但不改變位置 (避免回溯)
            if self.game_manager.player and reloaded_gm.player:
                 p_curr = self.game_manager.player
                 p_load = reloaded_gm.player
                 # 這裡假設 Player 類別有這些屬性，如果沒有可以直接覆蓋 player 物件
                 # 最簡單的方法是保留記憶體中的 player 位置，只更新數值
                 # 但為了保險，我們假設戰鬥不會移動位置，直接覆蓋 bag 即可
                 pass 

        if self.online_manager:
            self.online_manager.enter()

        # [New] 註冊網路聊天監聽
        if self.online_manager and hasattr(self.online_manager, "sio"):
            # 移除舊的監聽器避免重複
            try:
                self.online_manager.sio.off('chat_broadcast')
            except:
                pass

            @self.online_manager.sio.on('chat_broadcast')
            def on_chat_receive(data):
                # data 格式預期: {'id': 123, 'msg': 'Hello'}
                sender_id = data.get('id', '?')
                text = data.get('msg', '')
                self.chat_history.append({"from": f"P{sender_id}", "text": text})

        if self.online_manager:
            self.online_manager.enter()
        
    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()
##
    def open_overlay(self) -> None:
        self.is_overlay_open = True

    def close_overlay(self) -> None:
        self.is_overlay_open = False

    def toggle_setting_overlay(self) -> None:
        # 點按鈕時打開/關閉設定 overlay
        self.is_setting_open = not self.is_setting_open

    def on_volume_changed(self, value: float) -> None:
        # Slider 改變時被呼叫，value 在 0~100
        self.audio_volume = value
        # 呼叫 SoundManager 來調整 BGM 音量（0~1）
        sound_manager.set_bgm_volume(self.audio_volume / 100.0)
    # 滑桿 → on_volume_changed → sound_manager.set_bgm_volume → current_bgm.set_volume(...)

    def on_click_save(self) -> None:
        # 呼叫 GameManager.save
        self.game_manager.save("saves/game0.json")

    def on_click_load(self) -> None:
        # 呼叫 GameManager.load，並用新物件覆蓋現在的 game_manager
        new_gm = GameManager.load("saves/game0.json")
        if new_gm is not None:
            self.game_manager = new_gm
##[mine]

    # [New] 切換導航選單開關
    def toggle_nav(self):
        self.is_nav_open = not self.is_nav_open
        if self.is_nav_open:
            self._refresh_nav_buttons()

    # [New] 生成地點按鈕
    def _refresh_nav_buttons(self):
        self.nav_buttons = []
        start_x, start_y = 200, 240
        for i, place in enumerate(self.nav_places):
            btn = Button("UI/button_play.png", "UI/button_play_hover.png",
                         start_x, start_y + i * 50, 50, 40,
                         lambda p=place: self.start_navigation(p))
            self.nav_buttons.append(btn)

    # [New] 開始計算路徑
    def start_navigation(self, place):
        # 1. 取得目的地座標
        dest_pos = Position(place["x"] * GameSettings.TILE_SIZE, place["y"] * GameSettings.TILE_SIZE)
        
        # 2. 呼叫地圖找路 (BFS) - 記得 map.py 要有 find_path 方法
        path = self.game_manager.current_map.find_path(self.game_manager.player.position, dest_pos)
        
        # 3. 設定路徑給玩家 (Player 會存起來但不會自己走，只供畫圖用)
        if path:
            self.game_manager.player.path = path
            Logger.info(f"Path found: {len(path)} steps")
        else:
            Logger.info("No path found!")
            
        self.is_nav_open = False # 選完關閉選單

    # [New] 強制取消導航
    def stop_navigation(self):
        if self.game_manager.player:
            self.game_manager.player.path = []
            Logger.info("Navigation Stopped")
    def close_shop(self) -> None:
        self.is_shop_open = False

    # 切換商店模式
    def set_shop_mode(self, mode):
        self.shop_mode = mode
        self.refresh_shop_buttons()

    # 根據模式產生按鈕
    def refresh_shop_buttons(self):
        self.shop_dynamic_buttons = []
        start_x = self.shop_rect.x + 350
        start_y = self.shop_rect.y + 120
        
        if self.shop_mode == "BUY":
            # 建立原本的購買按鈕
            for i, item in enumerate(self.shop_items):
                btn = Button("UI/button_shop.png", "UI/button_shop_hover.png", 
                             start_x, start_y + i * 80, 60, 60, 
                             lambda it=item: self.buy_item(it))
                self.shop_dynamic_buttons.append(btn)
                
        elif self.shop_mode == "SELL":
            # 建立販賣按鈕 (讀取背包，排除 Coins)
            bag_items = [it for it in self.game_manager.bag._items_data if it["name"] != "Coins"]
            for i, item in enumerate(bag_items):
                name = item["name"]
                
                # [修正] 搜尋原始價格邏輯
                # 1. 先去 self.shop_items 裡面找看看有沒有賣這個東西
                found_item = next((x for x in self.shop_items if x["name"] == name), None)
                
                if found_item:
                    # 2. 如果有，就用它的 price (這裡就是你設定的 100)
                    price = found_item["price"] //2
                else:
                    # 3. 如果商店沒賣這個 (例如稀有道具)，給個預設值
                    price=10
                btn = Button("UI/button_shop.png", "UI/button_shop_hover.png", 
                             start_x, start_y + i * 80, 60, 60, 
                             lambda n=item["name"], p=price: self.sell_item(n, p))
                self.shop_dynamic_buttons.append(btn)

    # [New] 販賣邏輯
    def sell_item(self, name, price):
        bag = self.game_manager.bag
        target = next((x for x in bag._items_data if x["name"] == name), None)
        coins = next((x for x in bag._items_data if x["name"] == "Coins"), None)
        
        if target and target.get("count", 0) > 0 and coins:
            target["count"] -= 1
            coins["count"] = coins.get("count", 0) + price
            # 如果賣光了，從背包移除 (看你想不想留著)
            if target["count"] == 0:
                bag._items_data.remove(target)
            
            Logger.info(f"Sold {name} for {price}")
            self.game_manager.save("saves/game0.json")
            self.refresh_shop_buttons() # 重新整理列表
    def buy_item(self, item_info: dict) -> None:
        # 1. 檢查錢夠不夠
        bag = self.game_manager.bag
        
        # 找出 Coins 的數量
        coins_data = next((x for x in bag._items_data if x["name"] == "Coins"), None)
        if not coins_data:
            Logger.info("No coins found in bag!")
            return
            
        current_money = coins_data.get("count", 0)
        cost = item_info["price"]
        
        if current_money >= cost:
            # 2. 先扣錢
            coins_data["count"] = current_money - cost
            
            # [Modified] 3. 給道具 (針對精靈做特殊處理)
            if item_info["name"] == "Guardian Fairy":
                # 檢查是否已經有了
                if not self.game_manager.has_fairy:
                    # A. 成功購買
                    self.game_manager.has_fairy = True
                    
                    # === [提示] 這裡加入提示訊息 ===
                    # 參數：文字, X座標, Y座標, 顏色(青色)
                    self.spawn_floating_text("★ Fairy Equipped! ★", 400, 300, (0, 255, 255))
                    Logger.info("Bought Guardian Fairy successfully!")
                    
                else:
                    # B. 已經有了 (退款 + 失敗提示)
                    coins_data["count"] += cost # 把錢加回去
                    
                    # === [提示] 失敗提示 ===
                    self.spawn_floating_text("You already have one!", 400, 300, (255, 50, 50))
                    Logger.info("Already has fairy, purchase cancelled.")
                    return # 結束，不執行下面的存檔
            else:
                # ... (原本處理一般道具的邏輯保持不變) ...
                target_item = next((x for x in bag._items_data if x["name"] == item_info["name"]), None)
                if target_item:
                    target_item["count"] = target_item.get("count", 0) + 1
                else:
                    bag._items_data.append({
                        "name": item_info["name"], 
                        "count": 1, 
                        "sprite_path": item_info["sprite_path"],
                        "effect_type": item_info.get("effect_type", "NONE"),
                        "value": item_info.get("value", 0)
                    })
                
                # 一般道具購買成功的提示 (選擇性)
                self.spawn_floating_text(f"+1 {item_info['name']}", 400, 300, (255, 255, 0))

            # 4. 存檔
            self.game_manager.save("saves/game0.json")
            

    # [Fix] 補上這個方法，解決 AttributeError
    def spawn_floating_text(self, text, x, y, color=(255, 255, 0)):
        # 確保 floating_texts 列表存在
        if not hasattr(self, "floating_texts"):
            self.floating_texts = []
            
        self.floating_texts.append({
            "text": text,
            "x": x,
            "y": y,
            "life": 1.5, # 存活 1.5 秒
            "color": color
        })

    # [New] 跳出任務詢問對話框
    def prompt_quest_dialogue(self, name, description, target, reward):
        self.pending_quest_data = {
            "name": name,
            "description": description,
            "target_count": target,
            "reward_coins": reward
        }
        self.is_dialogue_open = True
        Logger.info(f"Prompting quest: {name}")

    # [New] 玩家點選 Yes -> 真的接任務
    def accept_pending_quest(self):
        if self.pending_quest_data:
            data = self.pending_quest_data
            # 這裡呼叫的是 GameManager 裡的方法
            self.game_manager.accept_new_quest(
                data["name"], data["description"], 
                data["target_count"], data["reward_coins"]
            )
            
            self.notif_text = "Quest Accepted!"
            self.notif_timer = 2.0
            self.is_dialogue_open = False
            self.pending_quest_data = {}

    # [New] 玩家點選 No -> 關閉視窗
    def close_dialogue(self):
        self.is_dialogue_open = False
        self.pending_quest_data = {}


##
    @override
    def update(self, dt: float):
        # [Fix] 從 OnlineManager 讀取新訊息 (使用正確的方法名 get_recent_chat)
        if self.online_manager:
            recent_chats = self.online_manager.get_recent_chat(50)
            self.chat_history = []
            for msg in recent_chats:
                sender_id = msg.get('from', '?')
                text = msg.get('text', '')
                self.chat_history.append({"from": f"P{sender_id}", "text": text})

        # [New] 1. 聊天室開啟時的邏輯
        if self.chat_overlay.is_open:
            self.chat_overlay.update(dt)
          # 1. 準備怪獸資料
            my_mon = self.game_manager.bag._monsters_data[0] if self.game_manager.bag._monsters_data else None
            
            # 2. 傳送資料給 Server
            self.online_manager.update(
                self.game_manager.player.position.x, 
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name,
                self.game_manager.player.direction.name, # 傳送方向
                my_mon # 傳送怪獸
            )
            return # 阻擋後續邏輯

        # ... (中間按鍵判斷保持不變) ...

        # [New] 1. 聊天室邏輯
        if self.chat_overlay.is_open:
            self.chat_overlay.update(dt)
            # 打字時阻擋移動，但保持連線心跳
            if self.online_manager and self.game_manager.player:
                self.online_manager.update(
                    self.game_manager.player.position.x, 
                    self.game_manager.player.position.y,
                    self.game_manager.current_map.path_name,
                    self.game_manager.player.direction.name,
                    None
                )
            return # 阻擋後續邏輯

        # [Fix] 1. 按 Enter 打開聊天室 (最少改動版)
        if input_manager.key_down(pg.K_RETURN):
            self.chat_overlay.open()
        
        # Check if there is assigned next scene
        self.game_manager.try_switch_map()
 
        # [New] 1. 聊天室開啟時的邏輯
        if self.chat_overlay.is_open:
            self.chat_overlay.update(dt)

            # 按 X 強制關閉聊天室
            # 因為下面有 return，所以關閉的邏輯一定要寫在這裡面！
            if input_manager.key_down(pg.K_ESCAPE):
                self.chat_overlay.close()

            # 打字時阻擋移動，但保持連線心跳
            if self.online_manager and self.game_manager.player:
                self.online_manager.update(
                    self.game_manager.player.position.x, 
                    self.game_manager.player.position.y,
                    self.game_manager.current_map.path_name,
                    self.game_manager.player.direction.name,
                    None
                )
            
            #這裡 return 了，所以如果沒在上面寫關閉邏輯，程式就會永遠卡在這裡
            return

        # ... (後面原本的 Enter 開啟邏輯保持不變) ...

        
        # Check if there is assigned next scene
        self.game_manager.try_switch_map()

        # [New] 更新提示訊息計時器 (放在最前面)
        if self.notif_timer > 0:
            self.notif_timer -= dt

    # [New] 更新導航 UI
        self.btn_nav.update(dt)
        if self.is_nav_open:
            for btn in self.nav_buttons:
                btn.update(dt)
            return # 打開選單時阻擋移動
        
        # [New] 如果正在導航中 (有路徑)，才啟用 Stop 按鈕
        if self.game_manager.player and self.game_manager.player.path:
            self.btn_stop_nav.update(dt)

        if self.is_nav_open:
            for btn in self.nav_buttons: btn.update(dt)
            return
        
        # [New] 更新對話框 UI (最優先處理)
        if self.is_dialogue_open:
            self.btn_dialogue_yes.update(dt)
            self.btn_dialogue_no.update(dt)
            return # 阻擋後續移動
        
        # 2. [New] Quest UI 更新 (阻擋移動)
        if self.is_quest_open:
            self.btn_quest_close.update(dt)
            return
        
        # 3. 更新任務按鈕
        self.btn_quest.update(dt)

    ##[mine]  
        # [New] 更新商店按鈕 & 阻擋操作
       # 1. 商店更新 (最優先處理，並阻擋移動)
        if self.is_shop_open:
            self.button_shop_close.update(dt)
            
            # 更新分頁按鈕 (Buy / Sell)
            self.btn_tab_buy.update(dt)
            self.btn_tab_sell.update(dt)
            
            # 更新動態列表按鈕 (根據現在是買還是賣，按鈕會不同)
            for btn in self.shop_dynamic_buttons:
                btn.update(dt)
                
            return  # 關鍵：商店開著時直接 return，不執行後面的角色移動
##
       
        # Update player and other data
        if self.game_manager.player:
            self.game_manager.player.update(dt)
            
        # ==========================================
            # [酷炫創意] 1. 守護小精靈邏輯 (平滑跟隨)
            # ==========================================
            # [Modified] 只有擁有小精靈時才運算
            if self.game_manager.has_fairy:
                target_x = self.game_manager.player.position.x + 16
                target_y = self.game_manager.player.position.y + 16
                
                self.fairy_pos[0] += (target_x - self.fairy_pos[0]) * 0.1
                self.fairy_pos[1] += (target_y - self.fairy_pos[1]) * 0.1
                
                self.fairy_history.append(list(self.fairy_pos))
                if len(self.fairy_history) > 20:
                    self.fairy_history.pop(0)
                
                self.fairy_angle += dt * 5

            # [New] 測試復活機制：按 K 鍵模擬「受到致命傷」
            if input_manager.key_pressed(pg.K_k):
                if self.game_manager.has_fairy:
                    # 觸發復活！
                    self.game_manager.has_fairy = False # 小精靈消失
                    self.spawn_floating_text("★ REVIVED! ★", 
                                             self.game_manager.player.position.x, 
                                             self.game_manager.player.position.y - 50, 
                                             (0, 255, 255)) # 青色大字
                    Logger.info("Guardian Fairy protected you!")
                else:
                    # 沒有小精靈，模擬死亡
                    self.spawn_floating_text("ouch... (No Fairy)", 
                                             self.game_manager.player.position.x, 
                                             self.game_manager.player.position.y - 50, 
                                             (255, 0, 0)) # 紅色字
  
        
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)


        # 按住 Shift 加速
        # 注意：這裡假設你的 Player 物件有一個 'speed' 屬性
        # 如果沒效果，請檢查 src/entities/player.py 裡的變數名稱是否為 speed
        if self.game_manager.player:
            base_speed = 200.0  # 這是基礎速度，請根據你原本的手感調整
            
            if input_manager.key_down(pg.K_LSHIFT) or input_manager.key_down(pg.K_RSHIFT):
                self.game_manager.player.speed = base_speed * 2.5 # 加速 2.5 倍
            else:
                self.game_manager.player.speed = base_speed

        # Update player and other data
        if self.game_manager.player:
            self.game_manager.player.update(dt)
        
 ##[ myself ] 
        import random
        if random.random() < 0.2: 
            # 建立一個粒子字典
            self.particles.append({
                "x": random.randint(0, GameSettings.SCREEN_WIDTH), # 隨機 X 位置
                "y": -10, # 從螢幕上方外面開始
                "speed_x": random.uniform(-0.5, 0.5), # 隨機左右飄
                "speed_y": random.uniform(1.0, 3.0),  #隨機下墜速度
                "color": random.choice([(255, 192, 203), (255, 240, 245), (255, 105, 180)]), # 粉紅色系
                "size": random.randint(2, 5), # 大小
                "life": 255 # 透明度/生命週期
            })

        # 2. 移動粒子
        for p in self.particles[:]: # 使用切片複製一份來跑迴圈，因為我們會移除元素
            p["x"] += p["speed_x"]
            p["y"] += p["speed_y"]
            p["life"] -= 1 # 慢慢消失
            
            # 簡單的左右搖擺效果
            p["x"] += math.sin(time.time() * 5 + p["y"] * 0.05) * 0.5

            # 如果超出螢幕或消失，就移除
            if p["y"] > GameSettings.SCREEN_HEIGHT or p["life"] <= 0:
                self.particles.remove(p)        
         # 在這裡插入 bush 互動檢查 
            player_rect = self.game_manager.player.animation.rect
            # 1. 如果玩家跟 bush 碰撞
            # 2. 且這一幀有按下指定按鍵（例如 B 鍵）
            # [Modified] 草叢互動 (按 B 鍵)
        if self.game_manager.player and input_manager.key_pressed(pg.K_b):
             # 檢查是否踩在草叢上
             player_rect = self.game_manager.player.animation.rect
             if self.game_manager.current_map.check_bush_collision(player_rect):
                 
                 # 隨機決定：撿到道具 還是 遇到怪獸
                 import random
                 if random.random() < 0.5:
                     # --- 事件 A：撿到道具 ---
                     found_item = random.choice(["Potion", "Pokeball", "Strength Potion", "Defense Potion"])
                     # 增加道具到背包
                     bag = self.game_manager.bag
                     target = next((x for x in bag._items_data if x["name"] == found_item), None)
                     if target:
                         target["count"] = target.get("count", 0) + 1
                     else:
                         bag._items_data.append({"name": found_item, "count": 1, "sprite_path": "ingame_ui/potion.png"}) # 暫用 potion 圖
                     
                     Logger.info(f"You found a {found_item} in the bush!")
                     # [New] 設定畫面提示 (顯示 2 秒)
                     self.notif_text = f"You found a {found_item}!"
                     self.notif_timer = 2.0 
                     self.game_manager.save("saves/game0.json")
                     
                 
                 else:
                     # --- 事件 B：遭遇戰鬥 (特殊模式：無經驗，有掉落) ---
                     GameSettings.IS_BUSH_BATTLE = True  # 設定旗標告訴戰鬥場景
                     self.game_manager.save("saves/game0.json")
                     scene_manager.change_scene("battle")
                     
##
        # Update others
        self.game_manager.bag.update(dt)
        
        # [mine] Online Update & PVP Check
        if self.game_manager.player and self.online_manager:
            # 1. 準備怪獸資料 (取第一隻)
            my_mon = self.game_manager.bag._monsters_data[0] if self.game_manager.bag._monsters_data else None
            
            # 2. 傳送資料給 Server (包含方向，解決滑步問題)
            self.online_manager.update(
                self.game_manager.player.position.x, 
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name,
                self.game_manager.player.direction.name,  # <--- 關鍵：送出方向
                my_mon
            )
            
            # 3. PVP 互動檢查 (這是原本比較長的那段)
            my_pos = self.game_manager.player.position
            for p in self.online_manager.get_list_players():
                # 只檢查同一張地圖的玩家
                if p.get("map") != self.game_manager.current_map.path_name:
                    continue
                
                # 計算距離
                dist = ((my_pos.x - float(p.get("x", 0)))**2 + (my_pos.y - float(p.get("y", 0)))**2) ** 0.5
                
                # 如果距離小於 1.5 格 (約96像素)
                if dist < GameSettings.TILE_SIZE * 1.5:
                    # 且按下空白鍵 -> 觸發對戰
                    if input_manager.key_pressed(pg.K_SPACE):
                        enemy_mon = p.get("pokemon")
                        if enemy_mon:
                            # 設定對手資料並切換場景
                            GameSettings.PVP_ENEMY_DATA = enemy_mon
                            scene_manager.change_scene("battle")
                            return
                                
##  [myself] 
        # 更新設定 overlay 的按鈕 & slider
        self.button_setting_overlay.update(dt)
        if self.is_setting_open:
            self.slider_volume.update(dt)
            self.button_save.update(dt)
            self.button_load.update(dt)
            self.button_setting_back.update(dt)

        # 更新 overlay 相關按鈕
        #每一幀都更新右上角按鈕（滑鼠有沒有碰到、點到） 如果 overlay 有打開，再更新 back 按鈕
        self.button_overlay.update(dt)
        if self.is_overlay_open:
            self.button_back.update(dt)


#[mine]
            # 玩家按 SPACE 進戰鬥
        # [Modified] 玩家按 SPACE 互動 (戰鬥 或 商店)
        # [Modified] 玩家按 SPACE 互動 (戰鬥 或 商店)
        for enemy in self.game_manager.current_enemy_trainers:
            
            # 1. 手動計算距離 (因為隔著櫃台，原本的 detected 判定會失效)
            p_pos = self.game_manager.player.position
            e_pos = enemy.position
            # 歐幾里得距離公式
            dist = ((p_pos.x - e_pos.x)**2 + (p_pos.y - e_pos.y)**2)**0.5
            
            # 2. 判斷是否按下空白鍵
            if input_manager.key_pressed(pg.K_SPACE):
                from src.entities.enemy_trainer import EnemyTrainerClassification
                
                # 3. [關鍵修改] 判定條件放寬
                # 如果是商人 (MERCHANT)，只要距離在 2.5 格內 (TILE_SIZE * 2.5) 就允許互動
                is_merchant = (enemy.classification == EnemyTrainerClassification.MERCHANT)
                in_range_merchant = (is_merchant and dist <= GameSettings.TILE_SIZE * 2.5)
                
                # 條件：(原本的接觸判定) OR (你是商人且你在兩格半內)
                if enemy.detected or in_range_merchant:
                    
                    # --- 下面是原本的互動邏輯 ---
                    if is_merchant:
                        self.is_shop_open = True
                    else:
                        # 道館館主互動
                        if self.game_manager.current_map.path_name == "gym.tmx":
                            self.prompt_quest_dialogue(
                                name="Gym Challenge",
                                description="Defeat 5 Enemies",
                                target=5,
                                reward=1000
                            )
                            return

                        # 進戰鬥前先存檔
                        self.game_manager.save("saves/game0.json")
                        GameSettings.BATTLE_TYPE = "TRAINER"
                        scene_manager.change_scene("battle")
                    return

##
    @override
    def draw(self, screen: pg.Surface):
        # ==========================================
        # 1. 繪製遊戲世界 (World Rendering)
        # ==========================================
        cam = PositionCamera(0, 0)
        if self.game_manager.player:
            cam = self.game_manager.player.camera
            self.game_manager.current_map.draw(screen, cam)
            # ===== [New] 在大地圖上畫導航線 (GPS Line) =====
            if self.game_manager.player.path:
                screen_points = []
                
                # A. 起點：玩家目前的中心點 (連線才不會斷掉)
                player_center = Position(
                    self.game_manager.player.position.x + GameSettings.TILE_SIZE // 2,
                    self.game_manager.player.position.y + GameSettings.TILE_SIZE // 2
                )
                # 轉換成螢幕座標
                screen_points.append(cam.transform_position(player_center))
                
                # B. 路徑點：剩下的導航點
                for p in self.game_manager.player.path:
                    screen_points.append(cam.transform_position(p))
                
                # C. 畫線 (顏色: 青色, 寬度: 5)
                if len(screen_points) > 1:
                    pg.draw.lines(screen, (0, 255, 255), False, screen_points, 5)
            # ================================================
            self.game_manager.player.draw(screen, cam)
            
            # ==========================================
            #繪製守護小精靈 (Guardian Fairy)
            # ==========================================
            if self.game_manager.player and self.game_manager.has_fairy:
                # 1. 畫軌跡 (光尾)
                for i, pos in enumerate(self.fairy_history):
                    # 越後面的點越小、越透明
                    radius = int(i / 3) 
                    alpha = i * 10
                    trail_surf = pg.Surface((20, 20), pg.SRCALPHA)
                    # 顏色：青色 (0, 255, 255)
                    pg.draw.circle(trail_surf, (0, 255, 255, alpha), (10, 10), radius)
                    
                    # 轉換世界座標 -> 螢幕座標
                    screen_pos = cam.transform_position(Position(pos[0]-10, pos[1]-10))
                    screen.blit(trail_surf, screen_pos)

                # 2. 畫本體 (呼吸燈核心)
                # 計算呼吸大小 (5 ~ 8 之間浮動)
                core_size = 6 + math.sin(self.fairy_angle) * 2
                
                # 轉換本體座標
                f_screen = cam.transform_position(Position(self.fairy_pos[0], self.fairy_pos[1]))
                
                # 畫外發光 (半透明白圈)
                glow = pg.Surface((40, 40), pg.SRCALPHA)
                pg.draw.circle(glow, (255, 255, 255, 100), (20, 20), core_size + 4)
                screen.blit(glow, (f_screen[0]-20, f_screen[1]-20))
                
                # 畫核心 (實心白球)
                pg.draw.circle(screen, (255, 255, 255), (int(f_screen[0]), int(f_screen[1])), int(core_size))
            # ==========================================
        else:
            self.game_manager.current_map.draw(screen, cam)
        # [New] 繪製粒子特效 (Bloom Effect)
        # 只有在花園地圖才顯示 (假設地圖檔名包含 "garden")
        # 如果你想每張圖都有，可以把 if 拿掉
        if "garden" in self.game_manager.current_map.path_name:
            for p in self.particles:
                # 建立一個帶有透明度的 Surface
                particle_surf = pg.Surface((p["size"]*2, p["size"]*2), pg.SRCALPHA)
                
                # 畫圓形花瓣
                pg.draw.circle(particle_surf, (*p["color"], int(p["life"])), (p["size"], p["size"]), p["size"])
                
                # 畫到螢幕上
                screen.blit(particle_surf, (int(p["x"]), int(p["y"])))

       # [Modified] 繪製連線玩家 (含動畫邏輯)
        if self.online_manager:
            players = self.online_manager.get_list_players()
            cur_map = self.game_manager.current_map.path_name
            cam = self.game_manager.player.camera if self.game_manager.player else PositionCamera(0,0)

            # 清理離線玩家的狀態
            active_ids = [int(p.get("id", -1)) for p in players]
            for pid in list(self.online_animations.keys()):
                if pid not in active_ids: del self.online_animations[pid]
            for pid in list(self.online_player_states.keys()):
                if pid not in active_ids: del self.online_player_states[pid]

            for p in players:
                if p.get("map") == cur_map:
                    try:
                        pid = int(p.get("id", -1))
                        px = float(p.get("x", 0))
                        py = float(p.get("y", 0))
                        direction_str = str(p.get("direction", "DOWN")).lower()

                        # 初始化動畫
                        if pid not in self.online_animations:
                            from src.sprites import Animation
                            # 這裡可以用之前教的 pid % 2 換圖技巧
                            self.online_animations[pid] = Animation("character/ow1.png", ["down", "left", "right", "up"], 4, (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
                        
                        # 初始化狀態追蹤
                        if pid not in self.online_player_states:
                            self.online_player_states[pid] = {"last_pos": (px, py), "is_moving": False}

                        anim = self.online_animations[pid]
                        state = self.online_player_states[pid]

                        # [Logic] 判斷是否移動
                        last_x, last_y = state["last_pos"]
                        # 如果座標變化超過微小值，視為正在移動
                        is_moving = (abs(px - last_x) > 0.1 or abs(py - last_y) > 0.1)
                        
                        # 更新狀態
                        state["last_pos"] = (px, py)
                        state["is_moving"] = is_moving

                        # 設定動畫
                        anim.switch(direction_str) # 設定方向
                        anim.update_pos(Position(px, py))
                        
                        if is_moving:
                            anim.update(0.01) # 播放走路動畫
                        else:
                            anim.index = 0 # 沒動就站著 (第0幀)

                        anim.draw(screen, cam)
                        
                        # ID 標籤
                        txt = self.font_small.render(f"P{pid}", True, (255, 255, 255))
                        screen.blit(txt, cam.transform_position(Position(px, py - 20)))

                    except Exception:
                        pass
            
        # 繪製 NPC (Enemy Trainers / Merchants)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, cam)

        # ... (原本繪製 Map, Player, Enemy 的程式碼) ...
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, cam)
     


        # ==========================================
        # 2. 繪製 UI 層 (UI Layer)
        # ==========================================

        # 如果沒有打開任何全螢幕介面，才顯示右上角的按鈕
        if not self.is_overlay_open and not self.is_shop_open:
            self.button_overlay.draw(screen) # 背包按鈕
            # 如果設定介面沒開，才顯示設定按鈕
            if not self.is_setting_open:
                self.button_setting_overlay.draw(screen)

            

        # [New] 繪製任務按鈕
            self.btn_quest.draw(screen)
            # 補個文字標籤
            screen.blit(self.font_small.render("Quest", True, (0,0,0)), (self.btn_quest.hitbox.x+10, self.btn_quest.hitbox.y+20))

        # ... (原本的 Settings, Backpack, Shop 繪製代碼) ...

        # [New] 繪製任務視窗 (Quest Overlay)
        if self.is_quest_open:
            # 1. 半透明背景
            dim = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            screen.blit(dim, (0, 0))
            
            # 2. 視窗面板
            pg.draw.rect(screen, (245, 245, 220), self.quest_rect) # 米色底
            pg.draw.rect(screen, (255, 215, 0), self.quest_rect, 4) # 金色框
            
            # 3. 關閉按鈕
            self.btn_quest_close.draw(screen)
            
            # 4. 任務內容
            quest = self.game_manager.quest
            if quest:
                # 標題
                title = self.font_quest.render(f"Current Quest: {quest.get('name', 'None')}", True, (100, 50, 0))
                screen.blit(title, (self.quest_rect.x + 30, self.quest_rect.y + 30))
                
                # 說明與進度
                desc = quest.get("description", "No active quest.")
                curr = quest.get("current_count", 0)
                target = quest.get("target_count", 0)
                
                status_color = (0, 0, 0)
                status_text = f"Progress: {curr} / {target}"
                
                if quest.get("is_completed"):
                    status_text = "Status: COMPLETED!"
                    status_color = (0, 150, 0)
                
                screen.blit(self.font_quest.render(desc, True, (0,0,0)), (self.quest_rect.x + 30, self.quest_rect.y + 80))
                screen.blit(self.font_quest.render(status_text, True, status_color), (self.quest_rect.x + 30, self.quest_rect.y + 120))
                
                # 獎勵顯示
                reward = quest.get("reward_coins", 0)
                reward_txt = self.font_quest.render(f"Reward: ${reward} Coins", True, (200, 0, 0))
                screen.blit(reward_txt, (self.quest_rect.x + 30, self.quest_rect.y + 180))
            else:
                screen.blit(self.font_quest.render("No Quest Data Found.", True, (0,0,0)), (self.quest_rect.x + 30, self.quest_rect.y + 80))

        # [New] 繪製導航按鈕
        if not self.is_overlay_open and not self.is_shop_open:
            self.btn_nav.draw(screen)
            screen.blit(self.font_small.render("NAV", True, (0,0,0)), (self.btn_nav.hitbox.x+15, self.btn_nav.hitbox.y+20))
            
            # [New] 如果正在導航，顯示 Stop 按鈕
            if self.game_manager.player and self.game_manager.player.path:
                self.btn_stop_nav.draw(screen)
                screen.blit(self.font_small.render("STOP", True, (255,0,0)), (self.btn_stop_nav.hitbox.x+10, self.btn_stop_nav.hitbox.y+20))
            
            # 繪製選單列表 (調整文字位置)
            if self.is_nav_open:
                # 背景框
                bg = pg.Rect(100, 240, 140, len(self.nav_buttons)*50 + 20)
                pg.draw.rect(screen, (240, 240, 240), bg)
                pg.draw.rect(screen, (0,0,0), bg, 2)
                
                for i, btn in enumerate(self.nav_buttons):
                    btn.draw(screen)
                    name = self.nav_places[i]["name"]
                    
                    # [Modified] 文字畫在按鈕 "左邊"
                    # 1. 先 Render 文字算出寬度
                    txt_surf = self.font_small.render(name, True, (0,0,0))
                    # 2. 計算座標：按鈕左邊界 - 文字寬度 - 間距(10)
                    txt_x = btn.hitbox.x - txt_surf.get_width() - 10
                    txt_y = btn.hitbox.centery - txt_surf.get_height() // 2
                    
                    screen.blit(txt_surf, (txt_x, txt_y))
            
            
        # --- 設定介面 (Settings Overlay) ---

        if self.is_setting_open:
            # 半透明背景
            dim = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            screen.blit(dim, (0, 0))

            # 面板背景
            pg.draw.rect(screen, (230, 230, 230), self.setting_rect)
            pg.draw.rect(screen, (80, 80, 80), self.setting_rect, 2)

            # 元件
            self.button_setting_back.draw(screen)
            self.slider_volume.draw(screen)
            self.button_save.draw(screen)
            self.button_load.draw(screen)
            
            # 標題
            screen.blit(self.font_small.render("Settings", True, (0, 0, 0)), (self.setting_rect.x + 20, self.setting_rect.y + 20))

        # --- 背包介面 (Backpack Overlay) ---
        if self.is_overlay_open:
            dim = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            screen.blit(dim, (0, 0))

            pg.draw.rect(screen, (240, 240, 240), self.overlay_rect)
            pg.draw.rect(screen, (80, 80, 80), self.overlay_rect, 2)

            self.button_back.draw(screen)
            # 呼叫你原本寫好的 helper function 畫內容
            self.draw_bag_overlay_contents(screen)

        # --- 商店介面 (Shop Overlay) [美化版] ---
        if self.is_shop_open:
            # 1. 全螢幕變暗 (更深一點更有質感)
            dim = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dim.fill((0, 0, 0, 180)) 
            screen.blit(dim, (0, 0))

            # === 主面板樣式設定 ===
            panel_bg = (240, 240, 235)    # 米白底
            border_col = (60, 60, 60)     # 深灰框
            highlight_col = (255, 230, 150) # 選中時的亮黃色
            
            # 2. 畫主視窗
            pg.draw.rect(screen, panel_bg, self.shop_rect, 0, border_radius=15)
            pg.draw.rect(screen, border_col, self.shop_rect, 4, border_radius=15)
            
            # 3. 標題與分隔線
            mode_str = "BUY ITEMS" if self.shop_mode == "BUY" else "SELL ITEMS"
            title = self.font_quest.render(f"Poke Mart - {mode_str}", True, border_col)
            screen.blit(title, (self.shop_rect.x + 40, self.shop_rect.y + 30))
            
            # 畫一條橫線分隔標題
            pg.draw.line(screen, border_col, (self.shop_rect.x + 20, self.shop_rect.y + 70), (self.shop_rect.right - 20, self.shop_rect.y + 70), 2)

            # 4. 顯示金錢 (右上角金色區塊)
            coins = next((x.get("count", 0) for x in self.game_manager.bag._items_data if x["name"] == "Coins"), 0)
            money_txt = self.font_small.render(f"$ {coins}", True, (255, 255, 255))
            # 畫金色背景
            pg.draw.rect(screen, (218, 165, 32), (self.shop_rect.right - 150, self.shop_rect.y + 25, 120, 35), 0, border_radius=8)
            screen.blit(money_txt, (self.shop_rect.right - 140, self.shop_rect.y + 35))

            # === [左區] 商品列表 ===
            list_start_x = self.shop_rect.x + 50
            
            # 用來記住滑鼠現在指到哪個商品 (給右邊顯示詳情用)
            hovered_item_data = None 

            if self.shop_mode == "BUY":
                for i, btn in enumerate(self.shop_dynamic_buttons):
                    # 取得對應的商品資料
                    item = self.shop_items[i]
                    
                    # 偵測滑鼠懸停 -> 畫底色 + 記住資料
                    if btn.hitbox.collidepoint(input_manager.mouse_pos):
                        pg.draw.rect(screen, highlight_col, (list_start_x - 10, btn.hitbox.y - 5, 320, 60), 0, border_radius=5)
                        hovered_item_data = item
                    
                    # 畫按鈕
                    btn.draw(screen)
                    
                    # 畫文字 (名字 + 價格)
                    name_txt = self.font_small.render(item["name"], True, (0, 0, 0))
                    price_txt = self.font_small.render(f"${item['price']}", True, (0, 100, 0))
                    screen.blit(name_txt, (list_start_x, btn.hitbox.y + 15))
                    screen.blit(price_txt, (list_start_x + 200, btn.hitbox.y + 15))

            elif self.shop_mode == "SELL":
                 # 賣東西模式的列表繪製 (同理)
                 bag_items = [it for it in self.game_manager.bag._items_data if it["name"] != "Coins"]
                 for i, btn in enumerate(self.shop_dynamic_buttons):
                     if i < len(bag_items):
                         item = bag_items[i]
                         if btn.hitbox.collidepoint(input_manager.mouse_pos):
                             pg.draw.rect(screen, highlight_col, (list_start_x - 10, btn.hitbox.y - 5, 320, 60), 0, border_radius=5)
                             hovered_item_data = item
                         
                         btn.draw(screen)
                         # 顯示持有數量
                         txt = self.font_small.render(f"{item['name']} x{item.get('count',0)}", True, (0,0,0))
                         screen.blit(txt, (list_start_x, btn.hitbox.y + 15))

            # === [右區] 詳細資訊卡片 (Detail Panel) ===
            # 畫一個深色底框
            info_rect = pg.Rect(self.shop_rect.right - 350, self.shop_rect.y + 100, 300, 350)
            pg.draw.rect(screen, (230, 230, 220), info_rect, 0, border_radius=10) # 淺灰底
            pg.draw.rect(screen, border_col, info_rect, 2, border_radius=10)      # 深灰框

            if hovered_item_data:
                # 1. 顯示大圖示 (放大版)
                if hovered_item_data.get("sprite_path"):
                    try:
                        img = resource_manager.get_image(hovered_item_data["sprite_path"])
                        img = pg.transform.scale(img, (64, 64)) 
                        img_rect = img.get_rect(center=(info_rect.centerx, info_rect.y + 60))
                        screen.blit(img, img_rect)
                    except: pass
                
                # 2. 商品名稱
                name_surf = self.font_quest.render(hovered_item_data["name"], True, border_col)
                name_rect = name_surf.get_rect(center=(info_rect.centerx, info_rect.y + 110))
                screen.blit(name_surf, name_rect)
                
                # === [新增] 3. 顯示價格 (根據買或賣模式顯示不同價格) ===
                price_text = ""
                price_color = (0, 0, 0)
                
                if self.shop_mode == "BUY":
                    # 買東西：直接顯示 price
                    p = hovered_item_data.get("price", 0)
                    price_text = f"Price: ${p}"
                    price_color = (200, 0, 0) # 紅色代表花錢
                else:
                    # 賣東西：要重新計算賣價 (原價的一半)
                    # 先去商店列表找原價
                    original_item = next((x for x in self.shop_items if x["name"] == hovered_item_data["name"]), None)
                    if original_item:
                        sell_price = original_item["price"] // 2
                    else:
                        sell_price = 10 # 沒賣的東西給預設價
                    
                    price_text = f"Selling Price: ${sell_price}"
                    price_color = (0, 150, 0) # 綠色代表賺錢

                # 畫出價格
                price_surf = self.font_small.render(price_text, True, price_color)
                price_rect = price_surf.get_rect(center=(info_rect.centerx, info_rect.y + 140))
                screen.blit(price_surf, price_rect)

                # 4. 描述文字 (往下移一點，避開價格)
                # 嘗試取得描述，如果是背包物品可能沒有 desc，就去商店列表找
                desc = hovered_item_data.get("desc", "")
                if not desc:
                    found = next((x for x in self.shop_items if x["name"] == hovered_item_data["name"]), None)
                    if found: desc = found.get("desc", "")
                
                if not desc: desc = "No description."

                # 自動換行
                words = desc.split(' ')
                lines = []
                current_line = ""
                for word in words:
                    if len(current_line + word) < 25:
                        current_line += word + " "
                    else:
                        lines.append(current_line)
                        current_line = word + " "
                lines.append(current_line)
                
                for idx, line in enumerate(lines):
                    line_surf = self.font_small.render(line, True, (80, 80, 80))
                    screen.blit(line_surf, (info_rect.x + 20, info_rect.y + 170 + idx * 20)) # y 改成 170

            else:
                # 沒選中時的提示
                hint = self.font_small.render("Hover over an item...", True, (150, 150, 150))
                screen.blit(hint, (info_rect.centerx - 60, info_rect.centery))

            # 5. 繪製底部按鈕 (Tab 和 Close)
            self.btn_tab_buy.draw(screen)
            self.btn_tab_sell.draw(screen)
            self.button_shop_close.draw(screen)
            
            # Tab 文字
            screen.blit(self.font_small.render("Buy", True, (0,0,0)), (self.btn_tab_buy.hitbox.x+15, self.btn_tab_buy.hitbox.y+20))
            screen.blit(self.font_small.render("Sell", True, (0,0,0)), (self.btn_tab_sell.hitbox.x+15, self.btn_tab_sell.hitbox.y+20))

        if not self.is_overlay_open and not self.is_shop_open and not self.is_setting_open:
            self.draw_minimap(screen)

        # [New] 繪製畫面提示 (Notification Toast)
        if self.notif_timer > 0:
            # 1. 準備文字
            text_surf = self.font_small.render(self.notif_text, True, (255, 255, 255))
            
            # 2. 計算置中位置 (螢幕上方 100px 處)
            padding = 10
            bg_w = text_surf.get_width() + padding * 2
            bg_h = text_surf.get_height() + padding * 2
            center_x = GameSettings.SCREEN_WIDTH // 2
            center_y = 100
            
            bg_rect = pg.Rect(center_x - bg_w // 2, center_y - bg_h // 2, bg_w, bg_h)
            
            # 3. 畫黑底白框
            pg.draw.rect(screen, (0, 0, 0), bg_rect)
            pg.draw.rect(screen, (255, 255, 255), bg_rect, 2)
            
            # 4. 畫文字
            screen.blit(text_surf, (bg_rect.x + padding, bg_rect.y + padding))

            # ... (前面的 UI 繪製) ...

        # [New] 繪製對話框 (Dialogue Overlay)
        if self.is_dialogue_open and self.pending_quest_data:
            # 1. 畫背景框 (深藍色底 + 白框，像傳統 RPG)
            pg.draw.rect(screen, (0, 0, 50), self.dialogue_rect)
            pg.draw.rect(screen, (255, 255, 255), self.dialogue_rect, 4)
            
            # 2. 準備文字
            data = self.pending_quest_data
            title_txt = f"Quest Offer: {data['name']}"
            desc_txt = f"Objective: {data['description']}"
            reward_txt = f"Reward: ${data['reward_coins']}"
            confirm_txt = "Do you accept this challenge?"
            
            # 3. 繪製文字 (一行一行畫)
            # 標題 (金色)
            screen.blit(self.font_quest.render(title_txt, True, (255, 215, 0)), (self.dialogue_rect.x + 30, self.dialogue_rect.y + 20))
            # 內容 (白色)
            screen.blit(self.font_small.render(desc_txt, True, (255, 255, 255)), (self.dialogue_rect.x + 30, self.dialogue_rect.y + 60))
            screen.blit(self.font_small.render(reward_txt, True, (0, 255, 0)), (self.dialogue_rect.x + 30, self.dialogue_rect.y + 90))
            screen.blit(self.font_small.render(confirm_txt, True, (200, 200, 200)), (self.dialogue_rect.x + 30, self.dialogue_rect.y + 140))
            
            # 4. 繪製按鈕
            self.btn_dialogue_yes.draw(screen)
            self.btn_dialogue_no.draw(screen)
            
            # 按鈕文字提示
            screen.blit(self.font_small.render("Yes", True, (255, 255, 255)), (self.btn_dialogue_yes.hitbox.x+15, self.btn_dialogue_yes.hitbox.y+20))
            screen.blit(self.font_small.render("No", True, (255, 255, 255)), (self.btn_dialogue_no.hitbox.x+20, self.btn_dialogue_no.hitbox.y+20))
       
        # [Fix] 補上這行：繪製聊天室 (放在最上層)
        if hasattr(self, 'chat_overlay'):
            self.chat_overlay.draw(screen)
    def draw_bag_overlay_contents(self, screen: pg.Surface) -> None:
        bag = self.game_manager.bag

        x = self.overlay_rect.x + 20
        y = self.overlay_rect.y + 20

        # --- Monsters ---
        title = self.font_small.render("Monsters:", True, (0, 0, 0))
        screen.blit(title, (x, y))
        y += 25

        icon_size = 40  # 圖示大小

        for monster in bag._monsters_data:
            name = monster.get("name", "Unknown")
            hp = monster.get("hp", 0)
            max_hp = monster.get("max_hp", 0)
            level = monster.get("level", 1)
            sprite_path = monster.get("sprite_path", None)

            # 先畫圖片
            if sprite_path is not None:
                try:
                    img = resource_manager.get_image(sprite_path)
                    img = pg.transform.scale(img, (icon_size, icon_size))
                    screen.blit(img, (x, y))
                except Exception:
                    # 如果讀圖失敗就忽略，至少文字還在
                    pass

            # 再畫文字（往右偏移一點）
            text_str = f"{name} Lv.{level}  HP {hp}/{max_hp}"
            line = self.font_small.render(text_str, True, (0, 0, 0))
            screen.blit(line, (x + icon_size + 10, y + icon_size // 4))

            y += icon_size + 8  # 換到下一行

        y += 12

        # --- Items ---
        title = self.font_small.render("Items:", True, (0, 0, 0))
        screen.blit(title, (x, y))
        y += 25

        for item in bag._items_data:
            name = item.get("name", "Unknown")
            count = item.get("count", 1)
            sprite_path = item.get("sprite_path", None)

            # 物品 icon
            if sprite_path is not None:
                try:
                    img = resource_manager.get_image(sprite_path)
                    img = pg.transform.scale(img, (icon_size, icon_size))
                    screen.blit(img, (x, y))
                except Exception:
                    pass

            # 物品文字
            line = self.font_small.render(f"{name} x{count}", True, (0, 0, 0))
            screen.blit(line, (x + icon_size + 10, y + icon_size // 4))

            y += icon_size + 8

        # [New] 更新小地圖快取 (換地圖時執行一次)
    def _update_minimap_cache(self):
        current_map = self.game_manager.current_map
        if not current_map: return

        # 1. 取得地圖原始大小
        # tmxdata.width 是格數，乘上 TILE_SIZE 才是像素寬度
        world_w = current_map.tmxdata.width * GameSettings.TILE_SIZE
        world_h = current_map.tmxdata.height * GameSettings.TILE_SIZE
        
        # 2. 計算等比例縮放的高度
        ratio = self.minimap_size_w / world_w
        minimap_h = int(world_h * ratio)
        
        # 3. 建立快取圖片
        # 我們直接拿 map._surface (這是原本畫好的大地圖) 來縮放
        self.minimap_surface = pg.transform.smoothscale(current_map._surface, (self.minimap_size_w, minimap_h))
        self.minimap_rect = pg.Rect(self.minimap_margin, self.minimap_margin, self.minimap_size_w, minimap_h)
        self.minimap_cache_map_name = current_map.path_name
        self.minimap_scale = (ratio, ratio) # 儲存縮放比例供 draw 使用

    # [New] 繪製小地圖邏輯
    def draw_minimap(self, screen: pg.Surface):
        # 1. 檢查是否需要更新快取
        if self.game_manager.current_map.path_name != self.minimap_cache_map_name:
            self._update_minimap_cache()
            
        if not self.minimap_surface: return

        # 2. 畫背景與邊框
        # 畫一個半透明黑底讓地圖清楚一點
        padding = 4
        bg_rect = self.minimap_rect.inflate(padding*2, padding*2)
        pg.draw.rect(screen, (0, 0, 0), bg_rect) # 黑底
        pg.draw.rect(screen, (255, 255, 255), bg_rect, 2) # 白框
        
        # 3. 畫靜態地圖 (從快取讀取)
        screen.blit(self.minimap_surface, self.minimap_rect)

        # 4. 畫動態物件 (點點)
        scale_x, scale_y = self.minimap_scale
        base_x, base_y = self.minimap_rect.x, self.minimap_rect.y

        # 小工具：把世界座標轉成小地圖座標
        # 小工具：把世界座標轉成小地圖座標
        def to_mini(pos):
            # [Fix] 校正座標：加上半個格子的大小 (TILE_SIZE / 2)
            # 這樣小地圖上的點，就會代表角色的「正中心」，而不是左上角
            center_x = pos.x + GameSettings.TILE_SIZE / 2
            center_y = pos.y + GameSettings.TILE_SIZE / 2
            
            return (int(base_x + center_x * scale_x), int(base_y + center_y * scale_y))

        # (A) 畫自己 (綠色)
        if self.game_manager.player:
            pg.draw.circle(screen, (0, 255, 0), to_mini(self.game_manager.player.position), 3)

        # [New] 在小地圖上畫導航路徑 (粉紅色線條)
        if self.game_manager.player and self.game_manager.player.path:
            # 把世界座標路徑 -> 轉成小地圖座標點
            mini_points = [to_mini(p) for p in self.game_manager.player.path]
            
            # 把自己現在的位置加進去當起點，線條才連續
            current_mini_pos = to_mini(self.game_manager.player.position)
            mini_points.insert(0, current_mini_pos)
            
            if len(mini_points) > 1:
                pg.draw.lines(screen, (255, 0, 255), False, mini_points, 2)

        # (B) 畫 NPC (紅色=敵人, 黃色=商人)
        for enemy in self.game_manager.current_enemy_trainers:
            # 簡單判斷：如果是 merchant 就黃色，不然就紅色
            color = (255, 0, 0)
            if hasattr(enemy, "classification") and enemy.classification.value == "merchant":
                color = (255, 255, 0)
            pg.draw.circle(screen, color, to_mini(enemy.position), 3)

        # (C) 畫連線玩家 (藍色)
        if self.online_manager:
            for p in self.online_manager.get_list_players():
                if p.get("map") == self.game_manager.current_map.path_name:
                    px, py = float(p.get("x", 0)), float(p.get("y", 0))
                    # 這裡沒有 Position 物件，手動建一個臨時的
                    dummy_pos = type('obj', (object,), {'x': px, 'y': py}) 
                    pg.draw.circle(screen, (0, 100, 255), to_mini(dummy_pos), 3)
        
