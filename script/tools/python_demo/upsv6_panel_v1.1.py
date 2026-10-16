#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pygame
import time
import math
from collections import deque
import smbus

# -----------------------------
# Register addresses (constants)
# -----------------------------
WHO_AM_I = 0x00
VERSION  = 0x01
UUID0    = 0x02  # 32-bit
UUID1    = 0x06  # 32-bit
UUID2    = 0x0A  # 32-bit
OUT_VOLT = 0x0E  # 16-bit mV
IN_VOLT  = 0x10  # 16-bit mV
BAT_VOLT = 0x12  # 16-bit mV
MCU_VOLT = 0x14  # 16-bit mV
OUT_CURR = 0x16  # 16-bit mA
IN_CURR  = 0x18  # 16-bit mA
BAT_CURR = 0x1A  # 16-bit signed mA
TEMP     = 0x1C  # 8-bit signed °C
CR1      = 0x1D  # 8-bit
CR2      = 0x1E  # 8-bit (reserved)
SR1      = 0x1F  # 8-bit (status 1)
SR2      = 0x20  # 8-bit (status 2)
BAT_PROT = 0x21  # 16-bit mV
SHDN_CTD = 0x23  # 16-bit seconds
AUTO_VTH = 0x25  # 16-bit mV
RSV_LEN  = 0x27  # 16-bit length (buffer length)
OTA_REQ  = 0x29  # 16-bit W only, write 0xA5A5 to request
RUNTIME  = 0x2B  # 64-bit microseconds
CHG_DET  = 0x33  # 16-bit seconds
LED_CTL  = 0x35  # 8-bit

# CR1 bits
CR1_AUTO_START = 0  # BIT0

# SR1 bits
SR1_SW_STATUS   = 0
SR1_FAST        = 1
SR1_CHARGE      = 2
SR1_INPUT_LOW   = 3
SR1_OUTPUT_LOW  = 4
SR1_BAT_LOW     = 5
SR1_ADC_MISM    = 6
SR1_BAT_FAIL    = 7

# LED control bits
LED_I2C_ACK     = 0
LED_BAT_CHG     = 1
LED_BAT_DISCHG  = 2
LED_FAULT       = 3
LED_OK          = 4

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def to_twos_complement_16(n):
    return n & 0xFFFF

def from_twos_complement_8(v):
    v &= 0xFF
    return v - 256 if v & 0x80 else v

def from_twos_complement_16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v

# -------------------
# Minimal UI elements
# -------------------
class Button:
    def __init__(self, rect, text, on_click, font):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.on_click = on_click
        self.font = font
        self.enabled = True

    def handle(self, ev):
        if not self.enabled:
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                self.on_click()

    def draw(self, surf):
        color = (60, 120, 200) if self.enabled else (100, 100, 100)
        pygame.draw.rect(surf, color, self.rect, border_radius=10)
        pygame.draw.rect(surf, (20, 20, 30), self.rect, width=2, border_radius=10)
        txt = self.font.render(self.text, True, (255, 255, 255))
        surf.blit(txt, txt.get_rect(center=self.rect.center))

class Toggle:
    def __init__(self, rect, label, get_func, set_func, font):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.get_func = get_func
        self.set_func = set_func
        self.font = font

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                self.set_func(not self.get_func())

    def draw(self, surf):
        on = self.get_func()
        box = pygame.Rect(self.rect.x, self.rect.y, 22, 22)
        pygame.draw.rect(surf, (20, 20, 30), box, border_radius=4)
        pygame.draw.rect(surf, (200, 200, 200), box, width=2, border_radius=4)
        if on:
            pygame.draw.rect(surf, (80, 200, 120), box.inflate(-6, -6), border_radius=3)
        label_surf = self.font.render(self.label, True, (230, 230, 230))
        surf.blit(label_surf, (self.rect.x + 28, self.rect.y + 2))

class BitLamp:
    def __init__(self, pos, label, font):
        self.pos = pos
        self.label = label
        self.font = font
        self.state = False

    def set(self, v: bool):
        self.state = bool(v)

    def draw(self, surf):
        x, y = self.pos
        r = 8
        color = (80, 200, 120) if self.state else (60, 60, 60)
        pygame.draw.circle(surf, color, (x, y), r)
        pygame.draw.circle(surf, (20, 20, 30), (x, y), r, width=2)
        label_surf = self.font.render(self.label, True, (230, 230, 230))
        surf.blit(label_surf, (x + 14, y - 10))

class NumberField:
    def __init__(self, rect, get_func, set_func, font, suffix="", hit_inflate=(180, 10)):
        self.rect = pygame.Rect(rect)
        self.get_func = get_func
        self.set_func = set_func
        self.font = font
        self.suffix = suffix
        self.active = False
        self.buffer = ""
        self.hit_inflate = hit_inflate
        self.hit_rect = self.rect.inflate(*hit_inflate)

    def move_to(self, x, y):
        self.rect.topleft = (x, y)
        self.hit_rect = self.rect.inflate(*self.hit_inflate)

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.active = self.hit_rect.collidepoint(ev.pos)
            if self.active:
                self.buffer = str(self.get_func())
        if self.active and ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.active = False
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                try:
                    val = int(self.buffer.strip())
                    self.set_func(val)
                except ValueError:
                    pass
                self.active = False
            elif ev.key == pygame.K_BACKSPACE:
                self.buffer = self.buffer[:-1]
            else:
                if ev.unicode and (ev.unicode.isdigit() or (ev.unicode == '-' and len(self.buffer) == 0)):
                    self.buffer += ev.unicode

    def draw(self, surf):
        border = (120, 200, 255) if self.active else (90, 90, 110)
        pygame.draw.rect(surf, (30, 30, 40), self.rect, border_radius=6)
        pygame.draw.rect(surf, border, self.rect, width=2, border_radius=6)
        text_val = self.buffer if self.active else str(self.get_func())
        label = f"{text_val}{self.suffix}"
        txt = self.font.render(label, True, (240, 240, 240))
        surf.blit(txt, txt.get_rect(center=self.rect.center))
        if self.active and (pygame.time.get_ticks() // 500) % 2 == 0:
            caret = self.font.render("|", True, (240, 240, 240))
            cr = caret.get_rect()
            cr.midleft = (txt.get_rect(center=self.rect.center).right + 3, self.rect.centery - cr.h//2 + caret.get_height()//2)
            surf.blit(caret, cr)

# -----------------
# Tiny line charts
# -----------------
class TinyChart:
    def __init__(self, rect, title, series, font, unit="", maxlen=240):
        self.rect = pygame.Rect(rect)
        self.title = title
        self.series = series
        self.font = font
        self.unit = unit
        self.maxlen = maxlen
        self.data = {name: deque(maxlen=maxlen) for name, _ in series}

    def push(self, device):
        for name, getter in self.series:
            try:
                v = getter(device)
            except Exception:
                v = 0
            self.data[name].append(v)

    def _minmax(self):
        vals = [v for seq in self.data.values() for v in seq]
        if not vals:
            return 0, 1
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-6:
            hi = lo + 1.0
        pad = (hi - lo) * 0.1 + 1e-6
        return lo - pad, hi + pad

    def draw(self, surf):
        pygame.draw.rect(surf, (35, 45, 60), self.rect, border_radius=10)
        pygame.draw.rect(surf, (25, 30, 45), self.rect, width=2, border_radius=10)

        title_s = self.font.render(self.title, True, (240, 240, 240))
        surf.blit(title_s, (self.rect.x + 10, self.rect.y + 6))

        plot = self.rect.inflate(-16, -28)
        plot.y += 16
        
        # Verschiebe den Plot leicht nach rechts, um Platz fuer die Achsen-Beschriftung zu machen
        left_margin = 65 
        plot.x += left_margin
        plot.w -= left_margin
        
        pygame.draw.rect(surf, (18, 18, 24), plot, border_radius=8)

        lo, hi = self._minmax()
        rng = (hi - lo) or 1.0
        
        # Zeichne Y-Achsen Labels (Max & Min)
        hi_str = f"{int(hi)} {self.unit}"
        lo_str = f"{int(lo)} {self.unit}"
        hi_surf = self.font.render(hi_str, True, (150, 150, 160))
        lo_surf = self.font.render(lo_str, True, (150, 150, 160))
        surf.blit(hi_surf, (self.rect.x + 10, plot.y - 2))
        surf.blit(lo_surf, (self.rect.x + 10, plot.bottom - 16))

        for i in range(1, 3):
            y = plot.y + int(i * plot.h / 3)
            pygame.draw.line(surf, (55, 55, 70), (plot.x, y), (plot.right, y), width=1)

        colors = [(200, 200, 230), (120, 200, 140), (200, 160, 120)]
        for idx, (name, _getter) in enumerate(self.series):
            seq = self.data[name]
            if len(seq) < 2:
                continue
            pts = []
            for i, v in enumerate(seq):
                x = plot.x + int(i * (plot.w-1) / (self.maxlen-1))
                y = plot.bottom - int((v - lo) / rng * (plot.h-1))
                pts.append((x, y))
            pygame.draw.lines(surf, colors[idx % len(colors)], False, pts, 2)
            leg = self.font.render(name, True, colors[idx % len(colors)])
            surf.blit(leg, (plot.right - 100, self.rect.y + 6 + 18*idx))

# -----------------
# Helper formatting
# -----------------
def fmt_mv(v): return f"{v} mV"
def fmt_ma(v): return f"{v} mA"
def fmt_temp(s8): return f"{s8} °C"
def fmt_hex8(v): return f"0x{v & 0xFF:02X}"
def fmt_hex16(v): return f"0x{v & 0xFFFF:04X}"
def fmt_hex32(v): return f"0x{v & 0xFFFFFFFF:08X}"
def fmt_runtime_us(us):
    sec = us / 1_000_000.0
    h = int(sec // 3600); sec -= h * 3600
    m = int(sec // 60); sec -= m * 60
    return f"{h:02d}:{m:02d}:{sec:05.2f}"

# ----------------------
# Device read & behavior
# ----------------------
class ReadDevice:
    def __init__(self, i2c_address):
        self.bus = smbus.SMBus(1)
        self.i2c_address = i2c_address

        self.reg8  = {}
        self.reg16 = {}
        self.reg32 = {}
        self.reg64 = {}
        
        # Exponential Moving Average Buffer fuer saubere Tabellen-Zahlen
        self.ema = {}
        self.alpha = 0.03 # Extrem starke Glaettung (vorher 0.15)

        # Initialize registers safely (verhindert Absturz bei blockiertem I2C Bus)
        try:
            self.reg8[WHO_AM_I] = self.read8(WHO_AM_I)
            self.reg8[VERSION]  = self.read8(VERSION)
            self.reg8[CR1]      = self.read8(CR1)
            self.reg8[CR2]      = self.read8(CR2)
            self.reg8[SR1]      = self.read8(SR1)
            self.reg8[SR2]      = self.read8(SR2)
            self.reg8[LED_CTL]  = self.read8(LED_CTL)

            self.reg32[UUID0] = self.read32(UUID0)
            self.reg32[UUID1] = self.read32(UUID1)
            self.reg32[UUID2] = self.read32(UUID2)

            self.reg64[RUNTIME] = self.read64(RUNTIME)

            self.reg16[BAT_PROT] = self.read16(BAT_PROT)
            self.reg16[AUTO_VTH] = self.read16(AUTO_VTH)
            self.reg16[SHDN_CTD] = self.read16(SHDN_CTD)
            self.reg16[CHG_DET]  = self.read16(CHG_DET)
            self.reg16[RSV_LEN]  = self.read16(RSV_LEN)
        except Exception as e:
            print(f"[WARNUNG] I2C Init fehlgeschlagen: {e}. Warte auf Bus-Erholung...")
        
        # Initiale Fuellung der Sensor-Werte und des EMA-Buffers
        self.update_sensors(0.0)

    def _apply_ema(self, key, val):
        if key not in self.ema:
            self.ema[key] = val
        else:
            self.ema[key] = self.ema[key] * (1 - self.alpha) + val * self.alpha

    def read8(self, addr):
        return self.bus.read_byte_data(self.i2c_address, addr)

    def read16(self, addr):
        return self.bus.read_word_data(self.i2c_address, addr)

    def read32(self, addr):
        data = self.bus.read_i2c_block_data(self.i2c_address, addr, 4)
        return (data[3] << 24) | (data[2] << 16) | (data[1] << 8) | data[0]

    def read64(self, addr):
        data = self.bus.read_i2c_block_data(self.i2c_address, addr, 8)
        return (data[7] << 56) | (data[6] << 48) | (data[5] << 40) | (data[4] << 32) | \
               (data[3] << 24) | (data[2] << 16) | (data[1] << 8) | data[0]

    def write8(self, addr, value):
        self.bus.write_byte_data(self.i2c_address, addr, value & 0xFF)

    def write16(self, addr, value):
        self.bus.write_word_data(self.i2c_address, addr, value & 0xFFFF)

    def write32(self, addr, value):
        self.bus.write_i2c_block_data(self.i2c_address, addr, [(value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])

    def write64(self, addr, value):
        self.bus.write_i2c_block_data(self.i2c_address, addr, [(value >> 56) & 0xFF, (value >> 48) & 0xFF, (value >> 40) & 0xFF, (value >> 32) & 0xFF, 
                                                               (value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])

    def update_sensors(self, dt):
        """Update sensor values exactly ONCE per frame to save I2C bandwidth!"""
        dt = min(dt, 1.0)
        self.reg64[RUNTIME] = (self.reg64.get(RUNTIME, 0) + int(dt * 1_000_000)) & 0xFFFFFFFFFFFFFFFF

        # Slow-Update fuer Config-Register (1x pro Sekunde bei 30FPS), um die UI synchron zu halten
        self._frame = getattr(self, '_frame', 0) + 1
        if self._frame % 30 == 0:
            try:
                # Falls der Start fehlgeschlagen ist, WHO_AM_I und UUIDs einmalig nachladen!
                if self.reg8.get(WHO_AM_I, 0) == 0:
                    self.reg8[WHO_AM_I] = self.read8(WHO_AM_I)
                    self.reg8[VERSION]  = self.read8(VERSION)
                    self.reg32[UUID0] = self.read32(UUID0)
                    self.reg32[UUID1] = self.read32(UUID1)
                    self.reg32[UUID2] = self.read32(UUID2)

                self.reg8[CR1] = self.read8(CR1)
                self.reg8[LED_CTL] = self.read8(LED_CTL)
                self.reg16[BAT_PROT] = self.read16(BAT_PROT)
                self.reg16[AUTO_VTH] = self.read16(AUTO_VTH)
                self.reg16[SHDN_CTD] = self.read16(SHDN_CTD)
                self.reg16[CHG_DET]  = self.read16(CHG_DET)
            except Exception:
                pass

        try:
            # Read RAW values into reg16/8 AND apply them to the smoothed EMA buffer
            v = self.read16(IN_VOLT);   self.reg16[IN_VOLT] = v;  self._apply_ema(IN_VOLT, v)
            v = self.read16(OUT_VOLT);  self.reg16[OUT_VOLT] = v; self._apply_ema(OUT_VOLT, v)
            v = self.read16(MCU_VOLT);  self.reg16[MCU_VOLT] = v; self._apply_ema(MCU_VOLT, v)
            v = self.read16(BAT_VOLT);  self.reg16[BAT_VOLT] = v; self._apply_ema(BAT_VOLT, v)
            v = self.read16(OUT_CURR);  self.reg16[OUT_CURR] = v; self._apply_ema(OUT_CURR, v)
            v = self.read16(IN_CURR);   self.reg16[IN_CURR] = v;  self._apply_ema(IN_CURR, v)
            
            bat_c = from_twos_complement_16(self.read16(BAT_CURR))
            self.reg16[BAT_CURR] = bat_c; self._apply_ema(BAT_CURR, bat_c)

            temp = from_twos_complement_8(self.read8(TEMP))
            self.reg8[TEMP] = temp; self._apply_ema(TEMP, temp)
            
            self.reg8[SR1] = self.read8(SR1)
        except Exception:
            # Falls der I2C-Bus kurz blockiert ist (Timeout), behalten wir einfach 
            # fuer diesen Frame die alten Werte und stuerzen nicht ab!
            pass


# --------------
# Main UI screen
# --------------
class PanelApp:
    def __init__(self, device):
        pygame.init()
        pygame.display.set_caption("52Pi UPS Gen 6 Management UI Panel V1.1")
        self.screen = pygame.display.set_mode((1200, 740))
        self.clock = pygame.time.Clock()
        self.font  = pygame.font.SysFont("consolas,menlo,monospace", 18)
        self.font_small = pygame.font.SysFont("consolas,menlo,monospace", 16)
        self.device = device
        self.running = True
        self.last_snapshot = None
        self._build_widgets()

    def _get_bit(self, v, bit): return ((v >> bit) & 1) != 0
    def _set_bit(self, v, bit, on): return (v | (1 << bit)) if on else (v & ~(1 << bit))

    def _build_widgets(self):
        f = self.font
        
        def get_auto(): return self._get_bit(self.device.reg8.get(CR1, 0), CR1_AUTO_START)
        def set_auto(on):
            v = self.device.reg8.get(CR1, 0)
            v = self._set_bit(v, CR1_AUTO_START, on)
            self.device.write8(CR1, v)
            self.device.reg8[CR1] = v # Cache direkt aktualisieren
        self.cr1_toggle = Toggle((30, 420, 240, 26), "CR1.auto_start_mode", get_auto, set_auto, f)

        def led_get(bit): return self._get_bit(self.device.reg8.get(LED_CTL, 0), bit)
        def led_set(bit, on):
            v = self.device.reg8.get(LED_CTL, 0)
            v = self._set_bit(v, bit, on)
            self.device.write8(LED_CTL, v)
            self.device.reg8[LED_CTL] = v # Cache direkt aktualisieren
        self.led_toggles = []
        labels_bits = [("i2c_ack",LED_I2C_ACK),("bat_charge",LED_BAT_CHG),
                       ("bat_discharge",LED_BAT_DISCHG),("fault_report",LED_FAULT),
                       ("ok_report",LED_OK)]
        for i, (label, bit) in enumerate(labels_bits):
            row = i // 2
            col = i % 2
            x = 30 + col*170
            y = 456 + row*28
            t = Toggle((x, y, 160, 26),
                       f"LED.{label}",
                       lambda b=bit: led_get(b),
                       lambda on, b=bit: led_set(b, on),
                       f)
            self.led_toggles.append(t)

        self.num_fields = []
        def NF(rect, getf, setf, suffix):
            return NumberField(rect, getf, setf, self.font_small, suffix, hit_inflate=(180, 10))
        self.num_fields.append(("battery_protection_voltage", NF((30, 640, 260, 28),
            lambda: self.device.reg16.get(BAT_PROT, 0),
            lambda v: (self.device.write16(BAT_PROT, clamp(v, 6000, 8400)), self.device.reg16.update({BAT_PROT: clamp(v, 6000, 8400)})), " mV")))
        self.num_fields.append(("auto_start_voltage", NF((30, 672, 260, 28),
            lambda: self.device.reg16.get(AUTO_VTH, 0),
            lambda v: (self.device.write16(AUTO_VTH, clamp(v, 6000, 8400)), self.device.reg16.update({AUTO_VTH: clamp(v, 6000, 8400)})), " mV")))
        self.num_fields.append(("shutdown_countdown", NF((300, 640, 260, 28),
            lambda: self.device.reg16.get(SHDN_CTD, 0),
            lambda v: (self.device.write16(SHDN_CTD, clamp(v, 0, 3600)), self.device.reg16.update({SHDN_CTD: clamp(v, 0, 3600)})), " s")))
        self.num_fields.append(("charge_detect_interval_s", NF((300, 672, 260, 28),
            lambda: self.device.reg16.get(CHG_DET, 0),
            lambda v: (self.device.write16(CHG_DET, clamp(v, 1, 600)), self.device.reg16.update({CHG_DET: clamp(v, 1, 600)})), " s")))

        self.btn_sync = Button((820, 700, 160, 30), "Sync Setting", self.sync_settings, self.font_small)
        self.btn_ota  = Button((990, 700, 160, 30), "Request OTA", lambda: self.device.write16(OTA_REQ, 0xA5A5), self.font_small)

        # Die Graphen holen sich ihre Daten jetzt aus dem gecachten reg16 Dictionary (ungefiltert fuer schoene Spikes)
        self.chart_v = TinyChart(pygame.Rect(570, 270, 600, 140), "Voltages",
                                 [("V-out", lambda d: d.reg16.get(OUT_VOLT, 0)),
                                  ("V-in",  lambda d: d.reg16.get(IN_VOLT, 0))],
                                 self.font_small, unit="mV", maxlen=260)
        
        self.chart_c = TinyChart(pygame.Rect(570, 430, 600, 140), "Currents",
                                 [("I-out", lambda d: d.reg16.get(OUT_CURR, 0)),
                                  ("I-bat", lambda d: d.reg16.get(BAT_CURR, 0))],
                                 self.font_small, unit="mA", maxlen=260)

    def draw_section_title(self, x, y, title, w=540):
        bar = pygame.Rect(x, y, w, 28)
        pygame.draw.rect(self.screen, (45, 60, 90), bar, border_radius=10)
        pygame.draw.rect(self.screen, (25, 30, 45), bar, width=2, border_radius=10)
        txt = self.font.render(title, True, (250, 250, 250))
        self.screen.blit(txt, (x + 12, y + 4))
        return bar.bottom + 10

    def draw_kv(self, x, y, name, value):
        name_s = self.font.render(name, True, (200, 200, 210))
        val_s  = self.font.render(value, True, (240, 240, 240))
        self.screen.blit(name_s, (x, y))
        self.screen.blit(val_s,  (x + 210, y)) 
    def sync_settings(self):
        try:
            led = self.device.read8(LED_CTL)
            self.last_snapshot = {
                "auto_start_mode": 1 if (self.device.read8(CR1) & (1 << CR1_AUTO_START)) else 0,
                "LED_CTL_raw": fmt_hex8(led),
                "LED.bits": {
                    "i2c_ack":     1 if (led & (1<<LED_I2C_ACK)) else 0,
                    "fault_report":1 if (led & (1<<LED_FAULT)) else 0,
                    "ok_report":   1 if (led & (1<<LED_OK)) else 0,
                },
                "battery_protection_voltage": self.device.read16(BAT_PROT),
                "auto_start_voltage": self.device.read16(AUTO_VTH),
                "shutdown_countdown": self.device.read16(SHDN_CTD),
                "charge_detect_interval_s": self.device.read16(CHG_DET),
            }
        except Exception:
            pass # Sync failed, try again later

    def _layout_inputs(self, cfg_title_y):
        base_y = cfg_title_y + 32  
        row_h  = 52                 

        positions = [
            (30,  base_y + 0*row_h),   
            (30,  base_y + 1*row_h),   
            (300, base_y + 0*row_h),   
            (300, base_y + 1*row_h),   
        ]
        for (_, nf), (x, yy) in zip(self.num_fields, positions):
            nf.move_to(x, yy)

    def draw_snapshot_panel(self, x, y, w=600, h=90):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (35, 45, 60), rect, border_radius=10)
        pygame.draw.rect(self.screen, (25, 30, 45), rect, width=2, border_radius=10)
        title = self.font_small.render("Synced Settings (snapshot)", True, (240, 240, 240))
        self.screen.blit(title, (x + 10, y + 6))
        if not self.last_snapshot:
            hint = self.font_small.render("Press 'Sync Setting' to capture current values.", True, (200, 200, 210))
            self.screen.blit(hint, (x + 10, y + 28))
            return
        yy = y + 26
        kv = self.last_snapshot
        lines = [
            f"auto_start_mode: {kv['auto_start_mode']}   LED_CTL: {kv['LED_CTL_raw']}",
            f"LED bits: i2c_ack={kv['LED.bits']['i2c_ack']} charge={kv['LED.bits']['bat_charge']} discharge={kv['LED.bits']['bat_discharge']} fault={kv['LED.bits']['fault_report']} ok={kv['LED.bits']['ok_report']}",
            f"bat_prot: {kv['battery_protection_voltage']} mV   auto_start: {kv['auto_start_voltage']} mV   shutdown: {kv['shutdown_countdown']} s",
        ]
        for line in lines:
            s = self.font_small.render(line, True, (230, 230, 235))
            self.screen.blit(s, (x + 10, yy))
            yy += 18

    def draw(self):
        self.screen.fill((16, 18, 24))

        # --- Left: Live readings (Gecached!) ---
        y = self.draw_section_title(20, 16, "Live Readings", w=540)
        self.draw_kv(30, y, "WHO_AM_I", fmt_hex8(self.device.reg8.get(WHO_AM_I, 0))); y += 24
        self.draw_kv(30, y, "version",  fmt_hex8(self.device.reg8.get(VERSION, 0))); y += 24

        u0 = self.device.reg32.get(UUID0, 0); u1 = self.device.reg32.get(UUID1, 0); u2 = self.device.reg32.get(UUID2, 0)
        uuid_str = f"{u2:08X}-{u1:08X}-{u0:08X}"
        # lines = [uuid_str[i:i+22] for i in range(0, len(uuid_str), 22) if uuid_str[i:i+22]]
        self.draw_kv(30, y, "uuid", uuid_str); y += 22

        # Die Tabelle links nutzt nun die butterweich geglaetteten EMA-Werte! 
        for label, val in [
            ("output_voltage", fmt_mv(int(self.device.ema.get(OUT_VOLT, 0)))),
            ("input_voltage",  fmt_mv(int(self.device.ema.get(IN_VOLT, 0)))),
            ("battery_voltage",fmt_mv(int(self.device.ema.get(BAT_VOLT, 0)))),
            ("mcu_voltage",    fmt_mv(int(self.device.ema.get(MCU_VOLT, 0)))),
            ("output_current", fmt_ma(int(self.device.ema.get(OUT_CURR, 0)))),
            ("input_current",  fmt_ma(int(self.device.ema.get(IN_CURR, 0)))),
            ("battery_current",fmt_ma(int(self.device.ema.get(BAT_CURR, 0)))),
            ("temperature",    fmt_temp(int(self.device.ema.get(TEMP, 0)))),
        ]:
            self.draw_kv(30, y, label, val); y += 22
            
        run_us = self.device.reg64.get(RUNTIME, 0)
        self.draw_kv(30, y, "runtime", f"{fmt_runtime_us(run_us)}"); y += 22

        # --- Left middle: CR1 & LED ---
        y = self.draw_section_title(20, y + 6, "CR1 & LED Control", w=540)
        self.cr1_toggle.rect.topleft = (30, y + 6)
        self.cr1_toggle.draw(self.screen)

        base_y = y + 36
        for i, t in enumerate(self.led_toggles):
            row = i // 2; col = i % 2
            t.rect.topleft = (30 + col*240, base_y + row*28)
            t.draw(self.screen)

        led_raw_y = base_y + ((len(self.led_toggles)+1)//2)*28 + 8
        self.draw_kv(20, led_raw_y, "LED_CTL (raw)", fmt_hex8(self.device.reg8.get(LED_CTL, 0)))

        # --- Left bottom: Config (2 columns) ---
        cfg_title_y = self.draw_section_title(20, led_raw_y + 28, "Config (editable)", w=540)
        self._layout_inputs(cfg_title_y)
        for (name, nf) in self.num_fields:
            lab = self.font_small.render(name, True, (220, 220, 230))
            self.screen.blit(lab, (nf.rect.x, nf.rect.y - 16))
            nf.draw(self.screen)

        # --- Right: Status & Charts ---
        y = self.draw_section_title(570, 16, "Status & Control", w=600)
        sr1 = self.device.reg8.get(SR1, 0)
        lamps = [
            (SR1_SW_STATUS,   "5V on"),
            (SR1_FAST,        "12V fast"),
            (SR1_CHARGE,      "charging"),
            (SR1_INPUT_LOW,   "input_low"),
            (SR1_OUTPUT_LOW,  "output_low"),
            (SR1_BAT_LOW,     "battery_low"),
            (SR1_ADC_MISM,    "adc_mismatch"),
            (SR1_BAT_FAIL,    "battery_fail"),
        ]
        x0 = 580; y0 = y
        colx = [x0, x0+300]
        for i, (bit, label) in enumerate(lamps):
            col = i % 2
            row = i // 2
            lamp = BitLamp((colx[col], y0 + row*26), label, self.font_small)
            lamp.set(((sr1 >> bit) & 1) != 0)
            lamp.draw(self.screen)

        # Charts
        self.chart_v.draw(self.screen)
        self.chart_c.draw(self.screen)

        # Snapshot + Buttons
        self.draw_snapshot_panel(570, 580, w=600, h=90)
        self.btn_sync.draw(self.screen)
        self.btn_ota.draw(self.screen)

        pygame.display.flip()

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_q and (ev.mod & pygame.KMOD_CTRL):
                self.running = False

            for _name, nf in self.num_fields:
                nf.handle(ev)
            self.cr1_toggle.handle(ev)
            for t in self.led_toggles:
                t.handle(ev)
            self.btn_sync.handle(ev)
            self.btn_ota.handle(ev)

    def run(self):
        last = time.time()
        self.draw()
        while self.running:
            now = time.time()
            dt = now - last
            last = now
            # update device & charts once per frame
            self.device.update_sensors(dt)
            self.chart_v.push(self.device)
            self.chart_c.push(self.device)
            self.draw()
            self.handle_events()
            self.clock.tick(30)

def main():
    dev = ReadDevice(0x17)  
    app = PanelApp(dev)
    app.run()
    pygame.quit()

if __name__ == "__main__":
    main()
