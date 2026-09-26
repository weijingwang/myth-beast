"""Minimal visual novel engine. All story content lives in story.json - see README.md."""
import json
import os
import sys

import pygame

W, H = 1280, 720
FPS = 60
BOX_H = 200                     # height of the dialogue box at the bottom
SPRITE_SIZE = (400, 600)        # only used for missing-sprite placeholders
SPRITE_X = {"left": 0.2, "middle": 0.5, "right": 0.8}
STEP_TYPES = {"text", "chapter", "choice", "cutscene", "branch", "end"}
WHITE, BLACK, GOLD = (255, 255, 255), (0, 0, 0), (255, 220, 120)
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")


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

    def draw(self, surf, font):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
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
        self.title_buttons = [Button(t, (W // 2, 360 + i * 90), 300)
                              for i, t in enumerate(("Start", "About", "Quit"))]
        self.back_button = Button("Back", (W // 2, H - 100), 300)
        self.go_title()

    # ---- flow
    def go_title(self):
        self.mode = "title"
        self.assets.play_music(self.story.get("title_music"))

    def new_game(self):
        self.stats = dict(self.story["stats"])
        self.flags = set()
        self.bg, self.sprites = None, {}
        self.mode = "story"
        self.goto(self.story["start"])

    def goto(self, scene):
        self.scene, self.index = scene, -1
        self.next_step()

    def next_step(self):
        self.index += 1
        step = self.step = self.story["scenes"][self.scene][self.index]
        # Fields any step may carry. They persist until changed.
        if "bg" in step:
            self.bg = step["bg"]
        self.sprites.update(step.get("sprites", {}))   # null removes a sprite
        if "music" in step:
            self.assets.play_music(step["music"])
        if "sfx" in step:
            self.assets.sfx(step["sfx"])

        kind = step["type"]
        if kind == "branch":
            self.goto(self.lost_scene() or self.pick_branch(step))
        elif kind == "cutscene":
            self.timer = 0.0
        elif kind == "choice":
            n = len(step["options"])
            self.buttons = [Button(o["text"], (W // 2, 280 + i * 80 - (n - 1) * 40))
                            for i, o in enumerate(step["options"])]
        elif kind == "end":
            self.buttons = [Button("Return to title", (W // 2, H // 2 + 120), 400)]

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
        if "flag" in option:
            self.flags.add(option["flag"])
        if "goto" in option:   # stats get checked at that scene's closing branch
            return self.goto(option["goto"])
        lost = self.lost_scene()
        if lost:
            return self.goto(lost)
        self.next_step()

    def lost_scene(self):
        """Scene to jump to if a stat is below 0, else None."""
        lose = self.story.get("lose", {})
        if self.scene in lose.values():
            return None
        for stat, scene in lose.items():
            if self.stats[stat] < 0:
                return scene
        return None

    # ---- input / update
    def handle(self, event):
        advance = ((event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)
                   or (event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN)))
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
            if kind in ("text", "chapter", "cutscene") and advance:   # click skips a cutscene
                self.next_step()
            elif kind == "choice":
                for button, option in zip(self.buttons, self.step["options"]):
                    if button.clicked(event):
                        self.choose(option)
                        break
            elif kind == "end" and self.buttons[0].clicked(event):
                self.go_title()

    def update(self, dt):
        if self.mode == "story" and self.step["type"] == "cutscene":
            self.timer += dt
            if self.timer >= sum(s["duration"] for s in self.step["slides"]):
                self.next_step()

    # ---- drawing
    def text_center(self, text, font, y):
        lines = wrap(font, text, W - 200)
        y -= len(lines) * font.get_linesize() // 2
        for line in lines:
            img = font.render(line, True, WHITE)
            self.screen.blit(img, img.get_rect(midtop=(W // 2, y)))
            y += font.get_linesize()

    def draw_box(self, speaker, text):
        box = pygame.Surface((W, BOX_H), pygame.SRCALPHA)
        box.fill((0, 0, 0, 190))
        self.screen.blit(box, (0, H - BOX_H))
        y = H - BOX_H + 20
        if speaker:
            self.screen.blit(self.font.render(speaker, True, GOLD), (40, y))
            y += 40
        for line in wrap(self.font, text, W - 80):
            self.screen.blit(self.font.render(line, True, WHITE), (40, y))
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
        text = "   ".join(f"{k}: {v}" for k, v in self.stats.items())
        img = self.font.render(text, True, WHITE)
        pygame.draw.rect(self.screen, BLACK, img.get_rect(topleft=(20, 20)).inflate(20, 12))
        self.screen.blit(img, (20, 20))

    def draw(self):
        self.screen.fill(BLACK)
        if self.mode == "title":
            self.text_center(self.story.get("title", ""), self.big, 200)
            for b in self.title_buttons:
                b.draw(self.screen, self.font)
        elif self.mode == "about":
            self.text_center(self.story.get("about", ""), self.font, H // 2 - 60)
            self.back_button.draw(self.screen, self.font)
        else:
            kind = self.step["type"]
            if kind == "cutscene":
                self.draw_cutscene()
            elif kind in ("chapter", "end"):
                self.text_center(self.step.get("text", ""), self.big, H // 2 - (60 if kind == "end" else 0))
            else:   # text / choice
                if self.bg:
                    self.screen.blit(self.assets.image("bg", self.bg, (W, H), True), (0, 0))
                for pos, x in SPRITE_X.items():
                    if self.sprites.get(pos):
                        img = self.assets.image("sprites", self.sprites[pos], SPRITE_SIZE)
                        self.screen.blit(img, img.get_rect(midbottom=(int(W * x), H)))
                if kind == "text" or self.step.get("text"):
                    self.draw_box(self.step.get("speaker"), self.step.get("text", ""))
                if self.story.get("show_stats"):
                    self.draw_stats()
            if kind in ("choice", "end"):
                for b in self.buttons:
                    b.draw(self.screen, self.font)

    def run(self):
        self.running = True
        while self.running:
            dt = self.clock.tick(FPS) / 1000
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
