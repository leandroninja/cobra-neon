import pygame
import sys
import json
import math
import random
from collections import deque
from dataclasses import dataclass

# ── Constantes ────────────────────────────────────────────────────────────────
CELL     = 20
COLS     = 30
ROWS     = 30
GRID_W   = COLS * CELL   # 600
PANEL_W  = 200
SCREEN_W = GRID_W + PANEL_W  # 800
SCREEN_H = ROWS * CELL        # 600
FPS      = 60

BG       = (10,  5,  20)
GRID_C   = (25, 15,  45)
HEAD_C   = (190, 60, 255)
BODY_TOP = (150, 40, 220)
BODY_BOT = ( 60, 10, 100)
FOOD_C   = (255, 50, 150)
PWR_C    = (255, 165,  0)
WHITE    = (255, 255, 255)
GRAY     = (140, 140, 170)
GREEN    = ( 80, 255, 120)
PANEL_BG = ( 20, 10,  40)
PANEL_BD = (100, 40, 180)

SPEED_INIT    = 8
SPEED_MAX     = 22
POWERUP_EVERY = 5
PWR_DURATION  = 5000
SCORE_FILE    = "highscore.json"

MENU, PLAYING, PAUSED, GAME_OVER = range(4)


# ── Utilidades ────────────────────────────────────────────────────────────────
@dataclass
class Particle:
    x: float; y: float
    vx: float; vy: float
    life: float
    color: tuple


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def spawn_particles(buf, gx, gy, color, n=14):
    cx, cy = gx * CELL + CELL // 2, gy * CELL + CELL // 2
    for _ in range(n):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(1.5, 4.5)
        buf.append(Particle(cx, cy, math.cos(ang) * spd, math.sin(ang) * spd, 1.0, color))


def draw_text(surf, text, font, color, x, y, center=False):
    img = font.render(text, True, color)
    surf.blit(img, (x - img.get_width() // 2 if center else x, y))


def load_highscore():
    try:
        with open(SCORE_FILE) as f:
            return json.load(f).get("highscore", 0)
    except Exception:
        return 0


def save_highscore(score):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump({"highscore": score}, f)
    except Exception:
        pass


# ── Comida ────────────────────────────────────────────────────────────────────
class Food:
    def __init__(self, occupied):
        self.pulse = 0.0
        self.respawn(occupied)

    def respawn(self, occupied):
        while True:
            pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
            if pos not in occupied:
                self.pos = pos
                self.pulse = 0.0
                break

    def update(self, dt):
        self.pulse += dt * 0.004

    def draw(self, surf):
        cx = self.pos[0] * CELL + CELL // 2
        cy = self.pos[1] * CELL + CELL // 2
        r  = max(4, int(CELL // 2 - 2 + 2 * abs(math.sin(self.pulse))))
        glow_a = max(0, int(60 + 40 * abs(math.sin(self.pulse))))
        gs = pygame.Surface((CELL * 2, CELL * 2), pygame.SRCALPHA)
        pygame.draw.circle(gs, (*FOOD_C, glow_a), (CELL, CELL), CELL)
        surf.blit(gs, (cx - CELL, cy - CELL))
        pygame.draw.circle(surf, FOOD_C, (cx, cy), r)


# ── Power-up (estrela laranja) ────────────────────────────────────────────────
class PowerUp:
    def __init__(self):
        self.active = False
        self.pos    = (0, 0)
        self.pulse  = 0.0
        self.angle  = 0.0

    def spawn(self, occupied):
        while True:
            pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
            if pos not in occupied:
                self.pos    = pos
                self.active = True
                self.pulse  = 0.0
                self.angle  = 0.0
                break

    def update(self, dt):
        if self.active:
            self.pulse += dt * 0.005
            self.angle  = (self.angle + dt * 0.003) % (2 * math.pi)

    def draw(self, surf):
        if not self.active:
            return
        cx = self.pos[0] * CELL + CELL // 2
        cy = self.pos[1] * CELL + CELL // 2
        r  = max(4, int(CELL // 2 - 1 + 2 * abs(math.sin(self.pulse))))
        pts = []
        for i in range(10):
            a   = self.angle + i * math.pi / 5
            rad = r if i % 2 == 0 else r // 2
            pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
        if len(pts) >= 3:
            pygame.draw.polygon(surf, PWR_C, pts)
            pygame.draw.polygon(surf, WHITE, pts, 1)


# ── Desenho da cobra ──────────────────────────────────────────────────────────
def draw_snake(surf, segments, direction):
    n = len(segments)
    for i, (gx, gy) in enumerate(segments):
        t     = i / max(1, n - 1)
        color = lerp_color(BODY_TOP, BODY_BOT, t) if i > 0 else HEAD_C
        rect  = pygame.Rect(gx * CELL + 1, gy * CELL + 1, CELL - 2, CELL - 2)
        pygame.draw.rect(surf, color, rect, border_radius=5)
        if i == 0:
            eye_map = {
                (1, 0):  [(5, -4), (5,  4)],
                (-1, 0): [(-5,-4), (-5, 4)],
                (0, -1): [(-4,-5), (4, -5)],
                (0,  1): [(-4, 5), (4,  5)],
            }
            ecx = gx * CELL + CELL // 2
            ecy = gy * CELL + CELL // 2
            for ex, ey in eye_map.get(direction, [(3, -3), (3, 3)]):
                pygame.draw.circle(surf, WHITE, (ecx + ex, ecy + ey), 2)


# ── Painel lateral ────────────────────────────────────────────────────────────
def draw_panel(surf, fonts, score, highscore, level, pwr_timer):
    px  = GRID_W
    f_xl, f_lg, f_md, f_sm = fonts
    mid = px + PANEL_W // 2
    surf.fill(PANEL_BG, (px, 0, PANEL_W, SCREEN_H))
    pygame.draw.line(surf, PANEL_BD, (px, 0), (px, SCREEN_H), 2)

    draw_text(surf, "COBRA",          f_lg, HEAD_C, mid,  28, center=True)
    draw_text(surf, "NEON",           f_lg, PWR_C,  mid,  60, center=True)
    pygame.draw.line(surf, PANEL_BD, (px + 15, 98), (px + PANEL_W - 15, 98))

    draw_text(surf, "PONTOS",         f_sm, GRAY,   mid, 115, center=True)
    draw_text(surf, str(score),       f_xl, WHITE,  mid, 145, center=True)
    pygame.draw.line(surf, PANEL_BD, (px + 15, 192), (px + PANEL_W - 15, 192))

    draw_text(surf, "RECORDE",        f_sm, GRAY,   mid, 210, center=True)
    draw_text(surf, str(highscore),   f_lg, HEAD_C, mid, 243, center=True)
    pygame.draw.line(surf, PANEL_BD, (px + 15, 285), (px + PANEL_W - 15, 285))

    draw_text(surf, "NIVEL",          f_sm, GRAY,   mid, 303, center=True)
    draw_text(surf, str(level),       f_xl, WHITE,  mid, 333, center=True)

    if pwr_timer > 0:
        secs = pwr_timer / 1000
        draw_text(surf, "TURBO!",         f_sm, PWR_C, mid, 415, center=True)
        draw_text(surf, f"{secs:.1f}s",   f_lg, PWR_C, mid, 445, center=True)


# ── Jogo principal ────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Cobra Neon")
        self.fonts = (
            pygame.font.SysFont("consolas", 42, bold=True),
            pygame.font.SysFont("consolas", 26, bold=True),
            pygame.font.SysFont("consolas", 18),
            pygame.font.SysFont("consolas", 14),
        )
        self.clock     = pygame.time.Clock()
        self.highscore = load_highscore()
        self._build_bg()
        self._init_audio()
        self._init_menu_snake()
        self.state = MENU
        self._new_game()

    def _build_bg(self):
        self.bg_surf = pygame.Surface((GRID_W, SCREEN_H))
        self.bg_surf.fill(BG)
        for c in range(COLS + 1):
            pygame.draw.line(self.bg_surf, GRID_C, (c * CELL, 0), (c * CELL, SCREEN_H))
        for r in range(ROWS + 1):
            pygame.draw.line(self.bg_surf, GRID_C, (0, r * CELL), (GRID_W, r * CELL))

    def _init_audio(self):
        try:
            pygame.mixer.music.load("Invincible.mp3")
            pygame.mixer.music.set_volume(0.3)
            pygame.mixer.music.play(-1)
        except Exception:
            pass
        try:
            self.sfx_eat = pygame.mixer.Sound("coin.wav")
            self.sfx_eat.set_volume(0.6)
        except Exception:
            self.sfx_eat = None

    def _init_menu_snake(self):
        path = []
        for x in range(COLS):              path.append((x, 0))
        for y in range(1, ROWS):           path.append((COLS - 1, y))
        for x in range(COLS - 2, -1, -1): path.append((x, ROWS - 1))
        for y in range(ROWS - 2, 0, -1):  path.append((0, y))
        self.menu_path  = path
        self.menu_idx   = 0
        self.menu_snake = deque(maxlen=20)
        self.menu_timer = 0

    def _new_game(self):
        cx, cy           = COLS // 2, ROWS // 2
        self.snake       = deque([(cx, cy), (cx - 1, cy), (cx - 2, cy)])
        self.direction   = (1, 0)
        self.next_dir    = (1, 0)
        self.score       = 0
        self.level       = 1
        self.speed       = SPEED_INIT
        self.move_timer  = 0
        self.particles   = []
        self.flash       = 0
        self.eats        = 0
        self.pwr_timer   = 0
        occupied         = set(self.snake)
        self.food        = Food(occupied)
        self.powerup     = PowerUp()

    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            self._events()
            self._update(dt)
            self._draw()

    def _events(self):
        DIR_KEYS = {
            pygame.K_UP:    (0, -1), pygame.K_w: (0, -1),
            pygame.K_DOWN:  (0,  1), pygame.K_s: (0,  1),
            pygame.K_LEFT:  (-1, 0), pygame.K_a: (-1, 0),
            pygame.K_RIGHT: (1,  0), pygame.K_d: (1,  0),
        }
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_highscore(self.highscore)
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                k = event.key
                if k == pygame.K_ESCAPE:
                    save_highscore(self.highscore)
                    pygame.quit(); sys.exit()
                if self.state == MENU and k == pygame.K_RETURN:
                    self._new_game(); self.state = PLAYING
                elif self.state == PLAYING and k == pygame.K_p:
                    self.state = PAUSED
                elif self.state == PAUSED and k == pygame.K_p:
                    self.state = PLAYING
                elif self.state == GAME_OVER and k == pygame.K_RETURN:
                    self._new_game(); self.state = PLAYING
                if self.state == PLAYING and k in DIR_KEYS:
                    nd = DIR_KEYS[k]
                    if nd[0] + self.direction[0] != 0 or nd[1] + self.direction[1] != 0:
                        self.next_dir = nd

    def _update(self, dt):
        alive = []
        for p in self.particles:
            p.x += p.vx; p.y += p.vy; p.vy += 0.08; p.life -= dt * 0.002
            if p.life > 0:
                alive.append(p)
        self.particles = alive

        if self.flash > 0:
            self.flash = max(0, self.flash - dt)

        if self.state == MENU:
            self.menu_timer += dt
            if self.menu_timer >= 80:
                self.menu_timer = 0
                self.menu_idx   = (self.menu_idx + 1) % len(self.menu_path)
                self.menu_snake.appendleft(self.menu_path[self.menu_idx])
            self.food.update(dt)
            return

        if self.state != PLAYING:
            return

        if self.pwr_timer > 0:
            self.pwr_timer = max(0, self.pwr_timer - dt)

        self.food.update(dt)
        self.powerup.update(dt)

        self.move_timer += dt
        if self.move_timer < 1000 // self.speed:
            return
        self.move_timer = 0

        self.direction = self.next_dir
        hx, hy = self.snake[0]
        nx = (hx + self.direction[0]) % COLS  # atravessa paredes
        ny = (hy + self.direction[1]) % ROWS

        if (nx, ny) in self.snake:
            self.flash = 300
            spawn_particles(self.particles, hx, hy, (255, 50, 50), 25)
            if self.score > self.highscore:
                self.highscore = self.score
                save_highscore(self.highscore)
            self.state = GAME_OVER
            return

        self.snake.appendleft((nx, ny))

        ate_food = (nx, ny) == self.food.pos
        ate_pwr  = self.powerup.active and (nx, ny) == self.powerup.pos

        if ate_food:
            self.eats  += 1
            self.score += 2 if self.pwr_timer > 0 else 1
            self.level  = self.score // 5 + 1
            self.speed  = min(SPEED_INIT + self.level - 1, SPEED_MAX)
            if self.sfx_eat:
                self.sfx_eat.play()
            spawn_particles(self.particles, nx, ny, FOOD_C)
            occupied = set(self.snake)
            self.food.respawn(occupied)
            if self.eats % POWERUP_EVERY == 0:
                self.powerup.spawn(set(self.snake) | {self.food.pos})
        elif ate_pwr:
            self.score    += 5
            self.pwr_timer = PWR_DURATION
            self.powerup.active = False
            spawn_particles(self.particles, nx, ny, PWR_C, 20)
            if self.sfx_eat:
                self.sfx_eat.play()
        else:
            self.snake.pop()

        if self.score > self.highscore:
            self.highscore = self.score

    def _draw(self):
        self.screen.blit(self.bg_surf, (0, 0))

        if self.state == MENU:
            n = len(self.menu_snake)
            for i, (gx, gy) in enumerate(self.menu_snake):
                t     = i / max(1, n - 1)
                color = lerp_color(BODY_TOP, BODY_BOT, t) if i > 0 else HEAD_C
                pygame.draw.rect(self.screen, color,
                                 (gx * CELL + 1, gy * CELL + 1, CELL - 2, CELL - 2),
                                 border_radius=4)
        else:
            draw_snake(self.screen, self.snake, self.direction)

        self.food.draw(self.screen)
        self.powerup.draw(self.screen)

        for p in self.particles:
            r = max(1, int(p.life * 5))
            try:
                ps = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(ps, (*p.color, int(p.life * 220)), (r, r), r)
                self.screen.blit(ps, (int(p.x) - r, int(p.y) - r))
            except Exception:
                pass

        if self.flash > 0:
            fs = pygame.Surface((GRID_W, SCREEN_H), pygame.SRCALPHA)
            fs.fill((255, 0, 0, int(self.flash / 300 * 120)))
            self.screen.blit(fs, (0, 0))

        draw_panel(self.screen, self.fonts, self.score, self.highscore, self.level, self.pwr_timer)

        t_ms = pygame.time.get_ticks()
        f_xl, f_lg, f_md, _ = self.fonts
        mid = GRID_W // 2

        if self.state == MENU:
            pulse = abs((t_ms % 1800) / 900.0 - 1.0)
            tc    = (int(150 + 105 * pulse), int(40 * pulse), int(200 + 55 * pulse))
            draw_text(self.screen, "COBRA NEON",             f_xl, tc,     mid, 170, center=True)
            draw_text(self.screen, "As paredes nao te detêm!", f_md, WHITE, mid, 260, center=True)
            if (t_ms // 500) % 2 == 0:
                draw_text(self.screen, "ENTER para jogar",   f_lg, GREEN,  mid, 370, center=True)
            draw_text(self.screen, "Estrela laranja = TURBO!", f_md, PWR_C, mid, 450, center=True)
        elif self.state == PAUSED:
            self._draw_overlay("PAUSADO", "P para continuar", mid, f_xl, f_lg)
        elif self.state == GAME_OVER:
            self._draw_overlay("FIM DE JOGO", "ENTER para reiniciar", mid, f_xl, f_lg)

        pygame.display.flip()

    def _draw_overlay(self, title, subtitle, mid, f_xl, f_lg):
        ov = pygame.Surface((GRID_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        self.screen.blit(ov, (0, 0))
        draw_text(self.screen, title,    f_xl, HEAD_C, mid, SCREEN_H // 2 - 60, center=True)
        draw_text(self.screen, subtitle, f_lg, WHITE,  mid, SCREEN_H // 2 + 10, center=True)


if __name__ == "__main__":
    Game().run()
