from __future__ import annotations
import pygame as pg
from typing import Optional, Callable, List, Dict
from .component import UIComponent
from src.core.services import input_manager
from src.utils import Logger


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
        font_path: str = "assets/fonts/Minecraft.ttf"
    ) -> None:
        self.is_open = False
        self._input_text = ""
        self._cursor_timer = 0.0
        self._cursor_visible = True
        self._just_opened = False
        self._send_callback = send_callback
        self._get_messages = get_messages

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

    def draw(self, screen: pg.Surface) -> None:
        # Always draw recent messages faintly, even when closed
        msgs = self._get_messages(8) if self._get_messages else []
        sw, sh = screen.get_size()
        x = 10
        y = sh - 100
        
        # Draw background for messages
        if msgs:
            container_w = max(100, int((sw - 20) * 0.6))
            bg = pg.Surface((container_w, 90), pg.SRCALPHA)
            bg.fill((0, 0, 0, 90 if self.is_open else 60))
            _ = screen.blit(bg, (x, y))
            # Render last messages
            lines = list(msgs)[-8:]
            draw_y = y + 8
            for m in lines:
                sender = str(m.get("from", ""))
                text = str(m.get("text", ""))
                surf = self._font_msg.render(f"{sender}: {text}", True, (255, 255, 255))
                _ = screen.blit(surf, (x + 10, draw_y))
                draw_y += surf.get_height() + 4
        
        # If not open, skip input field
        if not self.is_open:
            return
            
        # Input box
        box_h = 28
        box_w = max(100, int((sw - 20) * 0.6))
        box_y = sh - box_h - 6
        
        # Background box
        bg2 = pg.Surface((box_w, box_h), pg.SRCALPHA)
        bg2.fill((0, 0, 0, 160))
        _ = screen.blit(bg2, (x, box_y))
        
        # [Filled TODO] Render Text
        txt = self._input_text
        text_surf = self._font_input.render(txt, True, (255, 255, 255))
        _ = screen.blit(text_surf, (x + 8, box_y + 4))
        
        # Caret
        if self._cursor_visible:
            cx = x + 8 + text_surf.get_width() + 2
            cy = box_y + 6
            pg.draw.rect(screen, (255, 255, 255), pg.Rect(cx, cy, 2, box_h - 12))