from __future__ import annotations
import pygame as pg
from typing import Optional, Callable, List, Dict
from .component import UIComponent
from src.core.services import input_manager
from src.utils import Logger
from src.interface.components.button import Button
from src.utils import GameSettings

class ChatOverlay(UIComponent):
    """Lightweight chat UI similar to Minecraft: toggle with a key, type, press Enter to send."""
    is_open: bool
    _input_text: str
    _cursor_timer: float
    _cursor_visible: bool
    _just_opened: bool
    _send_callback: Callable[[str], bool] | None    #  NOTE: This is a callable function, you need to give it a function that sends the message
    _get_messages: Callable[[int], list[dict]] | None # NOTE: This is a callable function, you need to give it a function that gets the messages
    _font_msg: pg.font.Font
    _font_input: pg.font.Font

    def __init__(
        self,
        send_callback: Callable[[str], bool] | None = None,
        get_messages: Callable[[int], list[dict]] | None = None,
        *,
        font_path: str = "assets/fonts/Minecraft.ttf",
        on_close_callback=None
    ) -> None:
        self.is_open = False
        self._input_text = ""
        self._cursor_timer = 0.0
        self._cursor_visible = True
        self._just_opened = False
        self._send_callback = send_callback
        self._get_messages = get_messages
        self.on_close_callback = on_close_callback # [New] 存起來

        # [New] 定義關閉按鈕 (放在聊天框的右上角)
        # 假設你的聊天框位置大約在 chat_x, chat_y
        # 這裡我們用相對位置，假設聊天框寬度是 300
        self.btn_close = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            20 + 750, GameSettings.SCREEN_HEIGHT-40, # 根據你的 draw 位置微調
            30, 30,
            self.close
        )

        # [Filled TODO] Initialize Fonts
        try:
            self._font_msg = pg.font.Font(font_path, 20)
            self._font_input = pg.font.Font(font_path, 20)
        except Exception:
            Logger.warning(f"Failed to load font {font_path}, using default system font.")
            self._font_msg = pg.font.SysFont("Arial", 20)
            self._font_input = pg.font.SysFont("Arial", 20)

    def open(self) -> None:
        if not self.is_open:
            self.is_open = True
            self._cursor_timer = 0.0
            self._cursor_visible = True
            self._just_opened = True

    def close(self) -> None:
        self.is_open = False
        if self.on_close_callback:
            self.on_close_callback()

    def _handle_typing(self) -> None:
        """
        Turn keyboard keys into characters that appear inside the chat box.
        """
        # Check shift for capitalization
        shift = input_manager.key_down(pg.K_LSHIFT) or input_manager.key_down(pg.K_RSHIFT)

        # [Filled TODO] Letters a-z
        for k in range(pg.K_a, pg.K_z + 1):
            if input_manager.key_pressed(k):
                ch = chr(ord('a') + (k - pg.K_a))
                self._input_text += (ch.upper() if shift else ch)

        # [Filled TODO] Numbers 0-9
        for k in range(pg.K_0, pg.K_9 + 1):
            if input_manager.key_pressed(k):
                self._input_text += str(k - pg.K_0)

        # Handle Space
        if input_manager.key_pressed(pg.K_SPACE):
            self._input_text += " "

        # Handle Backspace
        if input_manager.key_pressed(pg.K_BACKSPACE):
            if len(self._input_text) > 0:
                self._input_text = self._input_text[:-1]

        # [Filled TODO] Enter to send
        if input_manager.key_pressed(pg.K_RETURN) or input_manager.key_pressed(pg.K_KP_ENTER):
            txt = self._input_text.strip()
            # Check if text is not empty and callback exists
            if txt and self._send_callback:
                ok = False
                try:
                    # Call the callback function to send the message
                    ok = self._send_callback(txt)
                except Exception as e:
                    Logger.error(f"Error sending chat: {e}")
                    ok = False
                
                # If sent successfully, clear input
                if ok:
                    self._input_text = ""
            elif not txt:
                # Optional: Close if enter pressed on empty line
                pass

    def update(self, dt: float) -> None:
        if not self.is_open:
            return
        
        # [Filled TODO] Close on Escape
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.close()
            return

        # Typing logic
        if self._just_opened:
            self._just_opened = False
        else:
            self._handle_typing()
            
        # Cursor blink logic
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._cursor_visible = not self._cursor_visible
        self.btn_close.update(dt)

    def draw(self, screen):
        if not self.is_open: return

        # 1. 定義「輸入框」的位置
        input_h = 40
        input_y = GameSettings.SCREEN_HEIGHT - input_h - 20
        input_x = 20
        input_w = 300

        # 2. 定義「訊息顯示區」的位置
        msg_h = 300 
        msg_y = input_y - msg_h - 10
        msg_x = 20
        msg_w = 300

        # --- 繪圖開始 ---

        # A. 畫訊息區背景
        s = pg.Surface((msg_w, msg_h))
        s.set_alpha(150)
        s.fill((0, 0, 0))
        screen.blit(s, (msg_x, msg_y))
        
        # B. 畫歷史訊息
        if self._get_messages:
            msgs = self._get_messages(10) 
            
            for i, msg in enumerate(msgs):
                line_y = msg_y + 10 + i * 25
                
                # 組合文字
                text_content = f"{msg.get('from', '?')}: {msg.get('text', '')}"
                
                # [Fix 1] 使用 self._font_msg 而不是 self.font
                txt_surf = self._font_msg.render(text_content, True, (255, 255, 255))
                screen.blit(txt_surf, (msg_x + 10, line_y))

        # C. 畫輸入框
        pg.draw.rect(screen, (0, 0, 0), (input_x, input_y, input_w, input_h))       
        pg.draw.rect(screen, (255, 255, 255), (input_x, input_y, input_w, input_h), 2) 

        # D. 畫正在輸入的字
        # [Fix 2] 使用 self._input_text 而不是 self.chat_input
        # [Fix 3] 使用 self._font_input 而不是 self.font
        display_text = self._input_text + ("|" if self._cursor_visible else "")
        input_surf = self._font_input.render(display_text, True, (255, 255, 255))
        
        # 讓文字垂直置中
        text_y = input_y + (input_h - input_surf.get_height()) // 2
        screen.blit(input_surf, (input_x + 10, text_y))

        # E. 更新關閉按鈕的位置
        # [Fix] Button 使用的是 hitbox 屬性
        self.btn_close.hitbox.topleft = (msg_x + msg_w + 5, msg_y) 
        self.btn_close.draw(screen)