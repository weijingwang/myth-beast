"""Minimal visual novel engine. All story content lives in story.json - see README.md."""
import json
import os
import random
import sys

import pygame

W, H = 1280, 720
FPS = 60
BOX_H = 200                     # height of the dialogue box at the bottom
SPRITE_SIZE = (400, 600)        # only used for missing-sprite placeholders
SPRITE_X = {"left": 0.2, "middle": 0.5, "right": 0.8}
STEP_TYPES = {"text", "chapter", "choice", "cutscene", "branch", "end"}
WHITE, BLACK, GOLD = (255, 255, 255), (0, 0, 0), (255, 220, 120)
GREEN, RED = (120, 255, 120), (255, 110, 110)
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# ---- game feel. Tweak freely.
TEXT_SPEED = 50                  # typewriter letters per second
FAST_FORWARD_KEYS = (pygame.K_TAB, pygame.K_LCTRL, pygame.K_RCTRL)   # hold to skip text
DIM = (140, 140, 140)            # colour multiplier for sprites that aren't speaking
SHAKE_PIXELS = 4                 # how far the screen shakes
SHAKE_TIME = 0.2                 # seconds; the shake fades out over this time
# ---- title screen look
MENU_FONT = "georgia,baskerville,palatino,timesnewroman,dejavuserif"   # first one installed is used
TITLE_COLOUR = (28, 38, 66)      # deep navy, reads well on the sky
MENU_PANEL = (22, 30, 52)        # button colour (drawn see-through)
FADE_TIME = 0.8                  # seconds for a fade to black and back (chapters, new backgrounds, endings)
# Sound effects that also shake or flash the screen. A step can also say
# "shake": true or "flash": [r, g, b] itself.
SHAKE_SFX = {"bonk.wav", "crash.wav", "charge.wav", "door_burst.wav"}
FLASH_SFX = {"fire.wav": (255, 140, 30)}


# ---------------------------------------------------------------- story file
def load_story(path):
    try:
        with open(path, encoding="utf-8") as f:
            story = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"story.json error at line {e.lineno}, column {e.colno}: {e.msg}")
    validate(story)
    return story


def validate(story):
    """Catch typos at startup instead of mid-game."""
    scenes = story["scenes"]
    targets = [story["start"]] + list(story.get("lose", {}).values())
    for name, steps in scenes.items():
        last = steps[-1] if steps else {}
        jumps_away = last.get("type") == "choice" and all("goto" in o for o in last["options"])
        if last.get("type") not in ("end", "branch") and not jumps_away:
            sys.exit(f"story.json: scene '{name}' must finish with 'end', 'branch', "
                     "or a choice where every option has a 'goto'")
        for i, step in enumerate(steps, 1):
            if step.get("type") not in STEP_TYPES:
                sys.exit(f"story.json: scene '{name}' step {i} has unknown type {step.get('type')!r}")
            if step["type"] == "branch":
                if "else" not in step:
                    sys.exit(f"story.json: scene '{name}' step {i} (branch) needs an 'else'")
                targets += [r["goto"] for r in step.get("rules", [])] + [step["else"]]
            if step["type"] == "choice":
                targets += [o["goto"] for o in step["options"] if "goto" in o]
            if step["type"] == "cutscene" and not step.get("slides"):
                sys.exit(f"story.json: scene '{name}' step {i} (cutscene) has no slides")
    for t in targets:
        if t not in scenes:
            sys.exit(f"story.json: scene '{t}' is used but never defined")
    for stat in story.get("lose", {}):
        if stat not in story["stats"]:
            sys.exit(f"story.json: 'lose' uses stat '{stat}' which is not in 'stats'")


# ---------------------------------------------------------------- assets
class Assets:
    """Loads and caches files. Missing files warn instead of crashing."""

    def __init__(self, font):
        self.font = font
        self.images, self.sounds = {}, {}
        self.music = None
        try:
            pygame.mixer.init()
            self.audio = True
        except pygame.error:
            print("WARNING: no audio device, sound disabled")
            self.audio = False

    def image(self, folder, name, size, fit=False):
        key = (folder, name)
        if key not in self.images:
            try:
                img = pygame.image.load(os.path.join(ASSETS, folder, name)).convert_alpha()
                if fit and img.get_size() != size:
                    img = pygame.transform.smoothscale(img, size)
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing image assets/{folder}/{name}")
                img = pygame.Surface(size)
                img.fill((90, 90, 90))
                label = self.font.render(f"{folder}/{name}", True, WHITE)
                img.blit(label, label.get_rect(center=(size[0] // 2, size[1] // 2)))
            self.images[key] = img
        return self.images[key]

    def sfx(self, name):
        if not self.audio:
            return
        if name not in self.sounds:
            try:
                self.sounds[name] = pygame.mixer.Sound(os.path.join(ASSETS, "sfx", name))
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing sound assets/sfx/{name}")
                self.sounds[name] = None
        if self.sounds[name]:
            self.sounds[name].play()

    def play_music(self, name):
        """name=None stops the music. Same track as now keeps playing."""
        if not self.audio or name == self.music:
            return
        self.music = name
        pygame.mixer.music.stop()
        if name:
            try:
                pygame.mixer.music.load(os.path.join(ASSETS, "music", name))
                pygame.mixer.music.play(-1)
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing music assets/music/{name}")


# ---------------------------------------------------------------- UI helpers
def wrap(font, text, width):
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            test = f"{line} {word}".strip()
            if font.size(test)[0] <= width or not line:
                line = test
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


class Button:
    def __init__(self, text, center, width=600, height=60):
        self.text = text
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = center

    def draw(self, surf, font, menu=False):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        if menu:   # title screen: see-through rounded panel, gold text on hover
            panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, MENU_PANEL + ((215,) if hover else (150,)), panel.get_rect(), border_radius=14)
            if hover:
                pygame.draw.rect(panel, GOLD, panel.get_rect(), width=2, border_radius=14)
            surf.blit(panel, self.rect)
            label = font.render(self.text, True, GOLD if hover else WHITE)
        else:
            pygame.draw.rect(surf, (110, 110, 170) if hover else (60, 60, 100), self.rect)
            label = font.render(self.text, True, WHITE)
        surf.blit(label, label.get_rect(center=self.rect.center))

    def clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos))


# ---------------------------------------------------------------- game
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        story_file = sys.argv[1] if len(sys.argv) > 1 else "story.json"   # python main.py tutorial.json
        self.story = load_story(os.path.join(HERE, story_file))
        pygame.display.set_caption(self.story.get("title", "Visual Novel"))
        self.font = pygame.font.Font(None, 36)
        self.big = pygame.font.Font(None, 80)
        self.assets = Assets(self.font)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont(MENU_FONT, 104, bold=True)
        self.menu_font = pygame.font.SysFont(MENU_FONT, 36)
        # menu stacked under the title on the left, leaving the bottom of the art clear
        self.title_buttons = [Button(t, (90 + 130, 268 + i * 70), 260, 58)
                              for i, t in enumerate(("Start", "About", "Quit"))]
        self.back_button = Button("Back", (W // 2, H - 100), 260, 58)
        self.dim_cache = {}
        self.fade, self.fade_from, self.prev_kind = 0.0, None, None
        self.go_title()

    # ---- flow
    def start_fade(self):
        """Fade the last shown frame to black, then fade the new one in."""
        held = pygame.key.get_pressed()
        if not self.fade and not any(held[k] for k in FAST_FORWARD_KEYS):
            self.fade_from, self.fade = self.screen.copy(), FADE_TIME

    def go_title(self):
        self.start_fade()
        self.mode = "title"
        self.assets.play_music(self.story.get("title_music"))

    def new_game(self):
        self.stats = dict(self.story["stats"])
        self.flags = set()
        self.bg, self.sprites = None, {}
        self.shake, self.flash, self.talking = 0.0, None, None
        self.popups, self.ff_timer = [], 0.0      # popups: [stat, delta, age]
        self.prev_kind = None
        self.mode = "story"
        self.goto(self.story["start"])

    def goto(self, scene):
        self.scene, self.index = scene, -1
        self.next_step()

    def next_step(self):
        self.index += 1
        step = self.step = self.story["scenes"][self.scene][self.index]
        kind = step["type"]
        if kind != "branch":   # fade on chapters, cutscenes, endings, new locations, or "fade": true
            auto = (kind in ("chapter", "cutscene", "end") or self.prev_kind in (None, "chapter", "cutscene")
                    or ("bg" in step and step["bg"] != self.bg))
            if step.get("fade", auto):   # "fade": false on a step turns it off
                self.start_fade()
            self.prev_kind = kind
        # Fields any step may carry. They persist until changed.
        if "bg" in step:
            self.bg = step["bg"]
        self.sprites.update(step.get("sprites", {}))   # null removes a sprite
        if "music" in step:
            self.assets.play_music(step["music"])
        if "sfx" in step:
            self.assets.sfx(step["sfx"])
        # game feel: typewriter restart, shake, flash, who is speaking
        self.typed = 0.0
        if step.get("shake") or step.get("sfx") in SHAKE_SFX:
            self.shake = SHAKE_TIME
        flash = step.get("flash") or FLASH_SFX.get(step.get("sfx"))
        if flash:
            self.flash = [tuple(flash), 0.5]
        self.talking = self.speaker_position(step)

        if kind == "branch":
            self.goto(self.lost_scene() or self.pick_branch(step))
        elif kind == "cutscene":
            self.timer = 0.0
        elif kind == "choice":
            n = len(step["options"])
            self.buttons = [Button(o["text"], (W // 2, 280 + i * 80 - (n - 1) * 40))
                            for i, o in enumerate(step["options"])]
        elif kind == "end":
            self.buttons = [Button("Return to title", (W // 2, H // 2 + 150), 400)]

    def speaker_position(self, step):
        """Sprite slot of the speaker. Sprite files start with the speaker's name
        ("Friend 1" -> friend1.png, "Knight 2" -> knight.png, "Claire (thinking)" -> claire_*.png)."""
        name = step.get("speaker", "").split("(")[0].lower().replace(" ", "")
        if not name:
            return None
        for key in (name, name.rstrip("0123456789")):
            for pos, sprite in self.sprites.items():
                if sprite and sprite.lower().startswith(key):
                    return pos
        return None

    def pick_branch(self, step):
        for rule in step.get("rules", []):
            ok = all(f in self.flags for f in rule.get("flags", []))
            if "stat" in rule:
                v = self.stats[rule["stat"]]
                ok = ok and rule.get("min", v) <= v <= rule.get("max", v)
            if ok:
                return rule["goto"]
        return step["else"]

    def choose(self, option):
        for stat, delta in option.get("stats", {}).items():
            self.stats[stat] += delta
            if delta:
                self.popups.append([stat, delta, 0.0])
        if "flag" in option:
            self.flags.add(option["flag"])
        if "goto" in option:   # stats get checked at that scene's closing branch
            return self.goto(option["goto"])
        lost = self.lost_scene()
        if lost:
            return self.goto(lost)
        self.next_step()

    def lost_scene(self):
        """Scene to jump to once a stat reaches 0, else None."""
        lose = self.story.get("lose", {})
        if self.scene in lose.values():
            return None
        for stat, scene in lose.items():
            if self.stats[stat] <= 0:
                return scene
        return None

    # ---- input / update
    def handle(self, event):
        advance = ((event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)
                   or (event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN)))
        if self.fade:   # ignore clicks mid-fade so nobody skips a line by accident
            return
        if self.mode == "title":
            start, about, quit_ = self.title_buttons
            if start.clicked(event):
                self.new_game()
            elif about.clicked(event):
                self.mode = "about"
            elif quit_.clicked(event):
                self.running = False
        elif self.mode == "about":
            if self.back_button.clicked(event):
                self.mode = "title"
        else:
            kind = self.step["type"]
            if kind == "text" and advance and self.typed < len(self.step["text"]):
                self.typed = len(self.step["text"])                    # first click finishes the line
            elif kind in ("text", "chapter", "cutscene") and advance:   # click skips a cutscene
                self.next_step()
            elif kind == "choice":
                for button, option in zip(self.buttons, self.step["options"]):
                    if button.clicked(event):
                        self.choose(option)
                        break
            elif kind == "end" and self.buttons[0].clicked(event):
                self.go_title()

    def update(self, dt):
        self.fade = max(0.0, self.fade - dt)
        if self.mode != "story":
            return
        if not self.fade:   # text starts typing once the fade is done
            self.typed += dt * TEXT_SPEED
        self.shake = max(0.0, self.shake - dt)
        if self.flash:
            self.flash[1] -= dt
            self.flash = self.flash if self.flash[1] > 0 else None
        for p in self.popups:
            p[2] += dt
        self.popups = [p for p in self.popups if p[2] < 2.0]
        kind = self.step["type"]
        keys = pygame.key.get_pressed()
        if kind in ("text", "chapter", "cutscene") and any(keys[k] for k in FAST_FORWARD_KEYS):
            self.ff_timer += dt
            if self.ff_timer > 0.05:
                self.ff_timer = 0.0
                return self.next_step()
        if kind == "cutscene":
            self.timer += dt
            if self.timer >= sum(s["duration"] for s in self.step["slides"]):
                self.next_step()

    # ---- drawing
    def text_center(self, text, font, y, colour=WHITE):
        lines = wrap(font, text, W - 200)
        y -= len(lines) * font.get_linesize() // 2
        for line in lines:
            img = font.render(line, True, colour)
            self.screen.blit(img, img.get_rect(midtop=(W // 2, y)))
            y += font.get_linesize()

    def draw_title_text(self, text, pos):
        """Big serif title with a soft white halo so it reads over sky and clouds."""
        halo = self.title_font.render(text, True, WHITE)
        halo.set_alpha(110)
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            self.screen.blit(halo, (pos[0] + dx, pos[1] + dy))
        self.screen.blit(self.title_font.render(text, True, TITLE_COLOUR), pos)

    def draw_box(self, speaker, text, shown=10**9):
        box = pygame.Surface((W, BOX_H), pygame.SRCALPHA)
        box.fill((0, 0, 0, 190))
        self.screen.blit(box, (0, H - BOX_H))
        y = H - BOX_H + 20
        if speaker:
            self.screen.blit(self.font.render(speaker, True, GOLD), (40, y))
            y += 40
        for line in wrap(self.font, text, W - 80):   # typewriter: only `shown` letters
            if shown <= 0:
                break
            self.screen.blit(self.font.render(line[:shown], True, WHITE), (40, y))
            shown -= len(line) + 1
            y += 34

    def draw_cutscene(self):
        slides, fade, t = self.step["slides"], self.step.get("fade", 1.0), self.timer
        i = 0
        while i < len(slides) - 1 and t >= slides[i]["duration"]:
            t -= slides[i]["duration"]
            i += 1
        self.screen.blit(self.assets.image("cutscenes", slides[i]["image"], (W, H), True), (0, 0))
        time_left = slides[i]["duration"] - t
        if i + 1 < len(slides) and time_left < fade:            # crossfade into next slide
            nxt = self.assets.image("cutscenes", slides[i + 1]["image"], (W, H), True)
            nxt.set_alpha(int(255 * (1 - time_left / fade)))
            self.screen.blit(nxt, (0, 0))
            nxt.set_alpha(255)

    def draw_stats(self):
        imgs = []
        for k, v in self.stats.items():   # a stat that just changed turns green/red
            changed = [d for s, d, _ in self.popups if s == k]
            colour = (GREEN if changed[-1] > 0 else RED) if changed else WHITE
            imgs.append(self.font.render(f"{k}: {v}", True, colour))
        width = sum(i.get_width() for i in imgs) + 30 * (len(imgs) - 1)
        pygame.draw.rect(self.screen, BLACK, pygame.Rect(20, 20, width, imgs[0].get_height()).inflate(20, 12))
        x = 20
        for img in imgs:
            self.screen.blit(img, (x, 20))
            x += img.get_width() + 30
        for i, (stat, delta, age) in enumerate(self.popups):   # "+1 Reputation" floating up
            img = self.big.render(f"{delta:+d} {stat}", True, GREEN if delta > 0 else RED)
            img.set_alpha(max(0, 255 - int(age * 127)))
            self.screen.blit(img, (30, 60 + i * 60 - int(age * 25)))

    def sprite_image(self, pos):
        name = self.sprites[pos]
        img = self.assets.image("sprites", name, SPRITE_SIZE)
        if self.talking and pos != self.talking:   # dim whoever isn't speaking
            if name not in self.dim_cache:
                self.dim_cache[name] = img.copy()
                self.dim_cache[name].fill(DIM + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            img = self.dim_cache[name]
        return img

    def draw(self):
        self.screen.fill(BLACK)
        if self.mode in ("title", "about") and self.story.get("title_bg"):
            self.screen.blit(self.assets.image("bg", self.story["title_bg"], (W, H), True), (0, 0))
        if self.mode == "title":
            self.draw_title_text(self.story.get("title", ""), (86, 70))
            for b in self.title_buttons:
                b.draw(self.screen, self.menu_font, menu=True)
        elif self.mode == "about":
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill(MENU_PANEL + (185,))
            self.screen.blit(veil, (0, 0))
            self.text_center(self.story.get("about", ""), self.menu_font, H // 2 - 60)
            self.back_button.draw(self.screen, self.menu_font, menu=True)
        else:
            kind = self.step["type"]
            if kind == "cutscene":
                self.draw_cutscene()
            elif kind in ("chapter", "end"):
                self.text_center(self.step.get("text", ""), self.big, H // 2 - (90 if kind == "end" else 0))
                if kind == "end" and self.step.get("hint"):   # small hint line under GAME OVER
                    self.text_center(self.step["hint"], self.menu_font, H // 2 + 45, GOLD)
            else:   # text / choice
                if self.bg:
                    self.screen.blit(self.assets.image("bg", self.bg, (W, H), True), (0, 0))
                for pos, x in SPRITE_X.items():
                    if self.sprites.get(pos):
                        img = self.sprite_image(pos)
                        self.screen.blit(img, img.get_rect(midbottom=(int(W * x), H)))
                if kind == "text":
                    self.draw_box(self.step.get("speaker"), self.step["text"], int(self.typed))
                elif self.step.get("text"):
                    self.draw_box(None, self.step["text"])
                if self.story.get("show_stats"):
                    self.draw_stats()
            if kind in ("choice", "end"):
                for b in self.buttons:
                    b.draw(self.screen, self.font)
            if self.flash:
                overlay = pygame.Surface((W, H))
                overlay.fill(self.flash[0])
                overlay.set_alpha(int(180 * self.flash[1] / 0.5))
                self.screen.blit(overlay, (0, 0))
            if self.shake:
                frame = self.screen.copy()
                self.screen.fill(BLACK)
                px = max(1, round(SHAKE_PIXELS * self.shake / SHAKE_TIME))   # fades out
                self.screen.blit(frame, (random.randint(-px, px), random.randint(-px, px)))
        if self.fade:   # first half: old frame darkens, second half: new frame appears
            t = 1 - self.fade / FADE_TIME
            if t < 0.5:
                self.screen.blit(self.fade_from, (0, 0))
            black = pygame.Surface((W, H))
            black.set_alpha(int(255 * (t * 2 if t < 0.5 else (1 - t) * 2)))
            self.screen.blit(black, (0, 0))

    def run(self):
        self.running = True
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.1)   # 60 FPS cap; a hitch never jumps animations ahead
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.handle(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
