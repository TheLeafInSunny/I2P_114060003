import pygame as pg
import pytmx
import heapq  # [New] A* 需要用到 Priority Queue
import math   # [New] 計算距離

from src.utils import load_tmx, Position, GameSettings, PositionCamera, Teleport

class Map:
    path_name: str
    tmxdata: pytmx.TiledMap
    spawn: Position
    teleporters: list[Teleport]
    _surface: pg.Surface
    _collision_map: list[pg.Rect]

    def __init__(self, path: str, tp: list[Teleport], spawn: Position):
        self.path_name = path
        self.tmxdata = load_tmx(path)
        self.spawn = spawn
        self.teleporters = tp

        pixel_w = self.tmxdata.width * GameSettings.TILE_SIZE
        pixel_h = self.tmxdata.height * GameSettings.TILE_SIZE

        self._surface = pg.Surface((pixel_w, pixel_h), pg.SRCALPHA)
        self._render_all_layers(self._surface)
        
        self._collision_map = self._create_collision_map()
        self._bush_rects = self._create_bush_rects()

        # 建構網格 (0=可走, 1=牆壁)
        self.width = self.tmxdata.width
        self.height = self.tmxdata.height
        self.grid = [[0 for _ in range(self.width)] for _ in range(self.height)]
        
        for rect in self._collision_map:
            gx = int(rect.x // GameSettings.TILE_SIZE)
            gy = int(rect.y // GameSettings.TILE_SIZE)
            if 0 <= gx < self.width and 0 <= gy < self.height:
                self.grid[gy][gx] = 1

    # [Modified] A* 尋路算法 (解決 BFS 的 L 型與鋸齒問題)
    def find_path(self, start_pos: Position, end_pos: Position) -> list[Position]:
        # 1. 轉換座標
        sx, sy = int(start_pos.x // GameSettings.TILE_SIZE), int(start_pos.y // GameSettings.TILE_SIZE)
        ex, ey = int(end_pos.x // GameSettings.TILE_SIZE), int(end_pos.y // GameSettings.TILE_SIZE)
        
        if not (0 <= sx < self.width and 0 <= sy < self.height): return []
        if not (0 <= ex < self.width and 0 <= ey < self.height): return []
        
        # A* 初始化
        # open_set 存: (f_score, g_score, x, y)
        open_set = []
        heapq.heappush(open_set, (0, 0, sx, sy))
        
        came_from = {}
        g_score = { (sx, sy): 0 }
        
        # 定義 8 個方向與移動代價 (Cost)
        # 直走代價 1.0，斜走代價 1.414 (根號2)
        # 這會讓電腦知道「斜走雖然只有一步，但比較遠」，所以它會嘗試拉直路徑
        moves = [
            (0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),   
            (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414) 
        ]
        
        found = False
        
        while open_set:
            # 取出分數最低 (最優) 的點
            _, current_g, cx, cy = heapq.heappop(open_set)
            
            if (cx, cy) == (ex, ey):
                found = True
                break
            
            for dx, dy, cost in moves:
                nx, ny = cx + dx, cy + dy
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    # 檢查是否可走 (grid == 0)
                    if self.grid[ny][nx] == 0:
                        
                        # [防穿牆優化] 切對角線時，檢查旁邊兩格
                        # 避免從兩個牆角的縫隙鑽過去
                        if abs(dx) == 1 and abs(dy) == 1:
                            if self.grid[cy][nx] == 1 or self.grid[ny][cx] == 1:
                                continue

                        # 計算新的代價 g
                        new_g = current_g + cost
                        
                        # 如果這條路比之前紀錄的更短，或是第一次走到
                        if (nx, ny) not in g_score or new_g < g_score[(nx, ny)]:
                            g_score[(nx, ny)] = new_g
                            # 啟發式函數 (Heuristic): 到終點的直線距離
                            h = math.sqrt((ex - nx)**2 + (ey - ny)**2)
                            f = new_g + h
                            
                            heapq.heappush(open_set, (f, new_g, nx, ny))
                            came_from[(nx, ny)] = (cx, cy)
                            
        if not found: return []
            
        # 3. 回溯路徑
        path = []
        curr = (ex, ey)
        
        half_tile = GameSettings.TILE_SIZE // 2 

        while curr in came_from:
            # 加上半格偏移，畫在路中央
            px = curr[0] * GameSettings.TILE_SIZE + half_tile
            py = curr[1] * GameSettings.TILE_SIZE + half_tile
            path.append(Position(px, py))
            
            if curr == (sx, sy): break
            curr = came_from.get(curr)
            if curr is None: break
            
        path.reverse()
        return path

    def update(self, dt: float): pass

    def draw(self, screen: pg.Surface, camera: PositionCamera):
        screen.blit(self._surface, camera.transform_position(Position(0, 0)))
        if GameSettings.DRAW_HITBOXES:
            for rect in self._collision_map:
                pg.draw.rect(screen, (255, 0, 0), camera.transform_rect(rect), 1)
        
    def check_collision(self, rect: pg.Rect) -> bool:
        for block in self._collision_map:
            if rect.colliderect(block): return True
        return False
        
    def check_teleport(self, pos: Position) -> Teleport | None:
        px, py = int(pos.x // GameSettings.TILE_SIZE), int(pos.y // GameSettings.TILE_SIZE)
        for tp in self.teleporters:
            if px == int(tp.pos.x // GameSettings.TILE_SIZE) and py == int(tp.pos.y // GameSettings.TILE_SIZE):
                return tp
        return None

    def _render_all_layers(self, target: pg.Surface) -> None:
        for layer in self.tmxdata.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                self._render_tile_layer(target, layer)
 
    def _render_tile_layer(self, target: pg.Surface, layer: pytmx.TiledTileLayer) -> None:
        for x, y, gid in layer:
            if gid == 0: continue
            img = self.tmxdata.get_tile_image_by_gid(gid)
            if img:
                img = pg.transform.scale(img, (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
                target.blit(img, (x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE))

    def _create_collision_map(self) -> list[pg.Rect]:
        rects = []
        for layer in self.tmxdata.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and ("collision" in layer.name.lower() or "house" in layer.name.lower()):
                for x, y, gid in layer:
                    if gid != 0:
                        rects.append(pg.Rect(x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
        return rects
    
    def check_bush_collision(self, rect: pg.Rect) -> bool:
        for b in self._bush_rects:
            if rect.colliderect(b): return True
        return False

    def _create_bush_rects(self) -> list[pg.Rect]:
        rects: list[pg.Rect] = []
        for layer in self.tmxdata.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and ("bush" in layer.name.lower()):
                for x, y, gid in layer:
                    if gid != 0:
                        rects.append(pg.Rect(x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
        return rects

    @classmethod
    def from_dict(cls, data: dict) -> "Map":
        tp = [Teleport.from_dict(t) for t in data["teleport"]]
        pos = Position(data["player"]["x"] * GameSettings.TILE_SIZE, data["player"]["y"] * GameSettings.TILE_SIZE)
        return cls(data["path"], tp, pos)

    def to_dict(self):
        return {
            "path": self.path_name,
            "teleport": [t.to_dict() for t in self.teleporters],
            "player": {
                "x": self.spawn.x // GameSettings.TILE_SIZE,
                "y": self.spawn.y // GameSettings.TILE_SIZE,
            }
        }