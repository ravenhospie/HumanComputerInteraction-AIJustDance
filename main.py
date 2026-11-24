import os
import queue
import subprocess
import sys
import threading
import time
from tkinter import filedialog
import cv2
import customtkinter as ctk
from PIL import Image, ImageTk
import pygame
from vision_engine import VisionEngine

pygame.mixer.init()

if sys.platform == "win32":
    import winsound

    def play_perfect_sound():
        winsound.Beep(1500, 110)

    def play_okay_sound():
        winsound.Beep(1100, 100)

    def play_bad_sound():
        winsound.Beep(350, 140)
else:
    def play_perfect_sound():
        print("\a", end="", flush=True)

    def play_okay_sound():
        print("[Audio] Good!", flush=True)

    def play_bad_sound():
        print("[Audio] Miss!", flush=True)


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

RTT_MOVES = ("CROWN_REACH", "EGYPTIAN_FRAME", "SHOULDER_POP_L", "SHOULDER_POP_R", "GROOVE_LOCK")


class CameraThread(threading.Thread):
    def __init__(self, engine, frame_queue, get_target_move_fn):
        super().__init__(daemon=True)
        self.engine = engine
        self.frame_queue = frame_queue
        self.get_target_move_fn = get_target_move_fn
        self.running = False

    def run(self):
        self.running = True
        print("[CameraThread] Game loop started.", flush=True)
        while self.running:
            try:
                target_move = self.get_target_move_fn()
                result, frame = self.engine.process_frame(draw=True, target_move=target_move)

                if frame is not None and result is not None:
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put((result, frame))
                else:
                    time.sleep(0.01)
            except Exception as e:
                print(f"[CameraThread Exception] {e}", flush=True)
                time.sleep(0.1)

    def stop(self):
        self.running = False


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("JUST DANCE AI — REMEMBER THE TIME")
        self.geometry("1320x960")
        self.minsize(1180, 820)
        self.configure(fg_color="#090c16")

        self.engine = VisionEngine()
        self.frame_queue = queue.Queue(maxsize=1)
        self.camera_thread = None
        self.is_active = False
        self._audio_proc = None

        self.video_path = None
        self.video_cap = None
        self.video_fps = 30.0
        self.audio_path = self._find_default_song()
        self.custom_move_icons = {}

        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.song_start_time = 0.0
        self.last_scored_window = None
        self.active_window_duration = 2.4

        # Choreography inspired by Michael Jackson's "Remember the Time"
        self.base_choreography = [
            (3.0, "CROWN_REACH"),
            (6.2, "EGYPTIAN_FRAME"),
            (9.4, "SHOULDER_POP_L"),
            (12.6, "SHOULDER_POP_R"),
            (15.8, "GROOVE_LOCK"),
            (19.0, "CROWN_REACH"),
            (22.2, "EGYPTIAN_FRAME"),
            (25.4, "SHOULDER_POP_L"),
            (28.6, "SHOULDER_POP_R"),
        ]
        self.routine_loop_length = 32.0

        self._build_ui()
        self._load_custom_move_images()
        self._schedule_gui_update()

    def _find_default_song(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for name in ("remember_the_time.wav", "remember_the_time.mp3", "background_song.mp3"):
            candidate = os.path.join(base_dir, name)
            if os.path.exists(candidate):
                return candidate

        search_dirs = [".", "music", "songs", "audio", "assets"]
        for folder in search_dirs:
            if not os.path.isdir(folder):
                continue
            for f in os.listdir(folder):
                if f.lower().endswith((".wav", ".mp3", ".ogg", ".m4a")) and "remember" in f.lower():
                    return os.path.join(folder, f)
        return None

    def _load_custom_move_images(self):
        if not os.path.isdir("moves"):
            return
        for move_name in RTT_MOVES:
            for ext in (".png", ".jpg", ".jpeg"):
                path = os.path.join("moves", f"{move_name}{ext}")
                if os.path.exists(path):
                    img = Image.open(path).resize((60, 60), Image.Resampling.LANCZOS)
                    self.custom_move_icons[move_name] = ImageTk.PhotoImage(img)
                    break

    def _build_ui(self):
        self.top_frame = ctk.CTkFrame(
            self,
            fg_color="#12172b",
            corner_radius=14,
            border_width=2,
            border_color="#253059",
        )
        self.top_frame.pack(fill="x", padx=18, pady=(12, 8))

        self.title_badge = ctk.CTkLabel(
            self.top_frame,
            text="JUST DANCE AI",
            font=("Arial", 22, "bold"),
            text_color="#00f5d4",
        )
        self.title_badge.pack(side="left", padx=(18, 16), pady=10)

        self.target_pill = ctk.CTkLabel(
            self.top_frame,
            text="MOVE: STAND BY",
            fg_color="#1c2340",
            corner_radius=8,
            padx=12,
            pady=4,
            font=("Arial", 13, "bold"),
            text_color="#7aa2f7",
        )
        self.target_pill.pack(side="left", padx=6)

        self.status_label = ctk.CTkLabel(
            self.top_frame,
            text="READY TO DANCE",
            text_color="#ffd166",
            font=("Arial", 15, "bold"),
        )
        self.status_label.pack(side="left", padx=12)

        self.tier_badge = ctk.CTkLabel(
            self.top_frame,
            text="",
            text_color="#39ff14",
            font=("Arial", 22, "bold"),
        )
        self.tier_badge.pack(side="left", padx=20)

        self.score_label = ctk.CTkLabel(
            self.top_frame,
            text="SCORE: 0   |   COMBO: 0x",
            font=("Arial", 18, "bold"),
            text_color="#00bbf9",
        )
        self.score_label.pack(side="right", padx=18)

        self.stage_frame = ctk.CTkFrame(
            self,
            fg_color="#0f1324",
            corner_radius=14,
            border_width=1,
            border_color="#1e2747",
        )
        self.stage_frame.pack(fill="both", expand=True, padx=18, pady=6)
        self.stage_frame.grid_columnconfigure(0, weight=1)
        self.stage_frame.grid_columnconfigure(1, weight=1)
        self.stage_frame.grid_rowconfigure(1, weight=1)

        self.ref_header = ctk.CTkLabel(
            self.stage_frame,
            text="REMEMBER THE TIME — DANCE VIDEO",
            font=("Arial", 12, "bold"),
            text_color="#a9b1d6",
        )
        self.ref_header.grid(row=0, column=0, pady=(8, 2))

        self.cam_header = ctk.CTkLabel(
            self.stage_frame,
            text="YOUR LIVE CAMERA",
            font=("Arial", 12, "bold"),
            text_color="#00f5d4",
        )
        self.cam_header.grid(row=0, column=1, pady=(8, 2))

        self.ref_video_label = ctk.CTkLabel(
            self.stage_frame,
            text=(
                "DANCE VIDEO SLOT\n\n"
                "Load a dance video (.MP4) below to mirror\n"
                "the moves alongside the bottom rhythm track"
            ),
            width=610,
            height=410,
            fg_color="#161b33",
            corner_radius=12,
            font=("Arial", 15, "bold"),
            text_color="#c0caf5",
        )
        self.ref_video_label.grid(row=1, column=0, padx=12, pady=(4, 12), sticky="nsew")

        self.video_label = ctk.CTkLabel(
            self.stage_frame,
            text="WEBCAM STANDBY\n\nPress 'START DANCE' to begin",
            width=610,
            height=410,
            fg_color="#161b33",
            corner_radius=12,
            font=("Arial", 15, "bold"),
            text_color="#c0caf5",
        )
        self.video_label.grid(row=1, column=1, padx=12, pady=(4, 12), sticky="nsew")

        self.track_container = ctk.CTkFrame(
            self,
            fg_color="#12172b",
            corner_radius=14,
            border_width=2,
            border_color="#253059",
        )
        self.track_container.pack(fill="x", padx=18, pady=6)

        self.track_title = ctk.CTkLabel(
            self.track_container,
            text="REMEMBER THE TIME MOVES — SLIDES INTO HIT ZONE & LIGHTS UP GREEN WHEN ACTIVE",
            font=("Arial", 11, "bold"),
            text_color="#7aa2f7",
        )
        self.track_title.pack(anchor="w", padx=16, pady=(6, 0))

        self.canvas = ctk.CTkCanvas(
            self.track_container,
            width=1250,
            height=136,
            bg="#0b0e1c",
            highlightthickness=0,
        )
        self.canvas.pack(fill="x", padx=12, pady=(4, 10))

        self.btn_frame = ctk.CTkFrame(
            self,
            fg_color="#12172b",
            corner_radius=14,
            border_width=1,
            border_color="#1e2747",
        )
        self.btn_frame.pack(fill="x", padx=18, pady=(4, 14))

        self.load_video_btn = ctk.CTkButton(
            self.btn_frame,
            text="LOAD DANCE VIDEO (.MP4)",
            command=self.select_dance_video,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=38,
            font=("Arial", 13, "bold"),
        )
        self.load_video_btn.pack(side="left", padx=(14, 8), pady=10)

        self.load_song_btn = ctk.CTkButton(
            self.btn_frame,
            text="LOAD SONG (.MP3 / .WAV)",
            command=self.select_song_file,
            fg_color="#6d28d9",
            hover_color="#5b21b6",
            height=38,
            font=("Arial", 13, "bold"),
        )
        self.load_song_btn.pack(side="left", padx=6, pady=10)

        vid_str = f"Video: {os.path.basename(self.video_path)}" if self.video_path else "Video: Optional"
        aud_str = f"Audio: {os.path.basename(self.audio_path)}" if self.audio_path else "Audio: Optional"
        self.media_info_label = ctk.CTkLabel(
            self.btn_frame,
            text=f"{vid_str}  |  {aud_str}",
            text_color="#9ece6a" if self.audio_path else "#c0caf5",
            font=("Arial", 13, "bold"),
        )
        self.media_info_label.pack(side="left", padx=14)

        self.start_btn = ctk.CTkButton(
            self.btn_frame,
            text="START DANCE",
            command=self.toggle_camera,
            fg_color="#16a34a",
            hover_color="#15803d",
            width=190,
            height=40,
            font=("Arial", 15, "bold"),
        )
        self.start_btn.pack(side="right", padx=14, pady=10)

    def _refresh_media_label(self):
        vid_str = f"Video: {os.path.basename(self.video_path)}" if self.video_path else "Video: Optional"
        aud_str = f"Audio: {os.path.basename(self.audio_path)}" if self.audio_path else "Audio: Optional"
        self.media_info_label.configure(text=f"{vid_str}  |  {aud_str}", text_color="#00f5d4")

    def select_song_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Song File",
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.m4a"), ("All Files", "*.*")],
        )
        if file_path:
            self.audio_path = file_path
            self._refresh_media_label()

    def select_dance_video(self):
        file_path = filedialog.askopenfilename(
            title="Select Reference Dance Video",
            filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv"), ("All Files", "*.*")],
        )
        if file_path:
            self.video_path = file_path
            self._refresh_media_label()
            preview_cap = cv2.VideoCapture(file_path)
            if preview_cap.isOpened():
                ret, frame = preview_cap.read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(rgb)
                    ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(610, 410))
                    self.ref_video_label.configure(image=ctk_img, text="")
                    self.ref_video_label.image = ctk_img
            preview_cap.release()

    def get_elapsed_time(self):
        if not self.is_active:
            return 0.0
        return max(0.0, time.time() - self.song_start_time)

    def _get_upcoming_and_active_moves(self, elapsed):
        current_cycle = int(elapsed // self.routine_loop_length)
        events = []
        for cycle in (max(0, current_cycle - 1), current_cycle, current_cycle + 1):
            offset = cycle * self.routine_loop_length
            for base_ts, move in self.base_choreography:
                ts = offset + base_ts
                is_active = ts <= elapsed < (ts + self.active_window_duration)
                events.append((ts, move, is_active))
        return events

    def get_current_target_move(self):
        if not self.is_active:
            return None
        elapsed = self.get_elapsed_time()
        for ts, move, is_active in self._get_upcoming_and_active_moves(elapsed):
            if is_active:
                return move
        return None

    def _start_music_sync(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.stop()
        except Exception as e:
            print(f"[Audio Notice] Mixer reset warning: {e}", flush=True)

        if getattr(self, "_audio_proc", None) is not None:
            try:
                self._audio_proc.terminate()
            except Exception:
                pass
            self._audio_proc = None

        if self.audio_path and os.path.exists(self.audio_path):
            played = False
            try:
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.set_volume(0.85)
                pygame.mixer.music.play(0)
                played = True
                print(f"[Audio] Playing via pygame: {os.path.basename(self.audio_path)}", flush=True)
            except Exception as e:
                print(f"[Audio Notice] pygame couldn't play {self.audio_path}: {e}", flush=True)

            if not played and sys.platform == "darwin":
                try:
                    self._audio_proc = subprocess.Popen(
                        ["afplay", self.audio_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print(f"[Audio] Playing via afplay: {os.path.basename(self.audio_path)}", flush=True)
                except Exception as af_err:
                    print(f"[Audio Notice] afplay failed: {af_err}", flush=True)
        else:
            print("[Audio Notice] No song loaded; timestamps still run from START DANCE.", flush=True)

    def toggle_camera(self):
        if not self.is_active:
            self._start_game()
        else:
            self._stop_game()

    def _start_game(self):
        print("[App] Starting dance game session...", flush=True)

        if not self.engine.open_camera(0):
            self.status_label.configure(text="CAMERA ERROR", text_color="#ff4d6d")
            return

        if self.video_path:
            cap = cv2.VideoCapture(self.video_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                self.video_fps = fps if fps and fps > 1.0 else 30.0
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.video_cap = cap
            else:
                self.video_cap = None
        else:
            self.video_cap = None

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass

        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.last_scored_window = None
        self.is_active = True

        # Start music and anchor the single shared timeline clock at the same instant
        self._start_music_sync()
        self.song_start_time = time.time()

        self.status_label.configure(text="DO THE MOVE WHEN IT LIGHTS UP GREEN!", text_color="#39ff14")
        self.tier_badge.configure(text="")
        self.start_btn.configure(text="STOP GAME", fg_color="#dc2626", hover_color="#b91c1c")
        self.load_video_btn.configure(state="disabled")
        self.load_song_btn.configure(state="disabled")

        self.camera_thread = CameraThread(
            self.engine, self.frame_queue, self.get_current_target_move
        )
        self.camera_thread.start()

    def _stop_game(self):
        print("[App] Stopping game session...", flush=True)
        self.is_active = False

        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

        if getattr(self, "_audio_proc", None) is not None:
            try:
                self._audio_proc.terminate()
            except Exception:
                pass
            self._audio_proc = None

        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None

        if hasattr(self.engine, "release_camera"):
            try:
                self.engine.release_camera()
            except Exception:
                pass

        if self.video_cap is not None:
            self.video_cap.release()
            self.video_cap = None

        self.target_pill.configure(text="MOVE: STAND BY", text_color="#7aa2f7")
        self.status_label.configure(
            text=f"SESSION COMPLETE (MAX COMBO: {self.max_combo}x)", text_color="#ffd166"
        )
        self.tier_badge.configure(text=f"SCORE: {self.score}", text_color="#00f5d4")
        self.start_btn.configure(text="START DANCE", fg_color="#16a34a", hover_color="#15803d")
        self.load_video_btn.configure(state="normal")
        self.load_song_btn.configure(state="normal")
        self.video_label.configure(
            image=None, text="WEBCAM STANDBY\n\nPress 'START DANCE' to play again"
        )
        self.ref_video_label.configure(
            image=None,
            text=(
                "DANCE VIDEO SLOT\n\n"
                "Load a dance video (.MP4) below to mirror\n"
                "the moves alongside the bottom rhythm track"
            ),
        )
        self.canvas.delete("all")

    def _update_reference_video_frame(self, elapsed):
        if self.video_cap is None or not self.video_cap.isOpened():
            return

        total_frames = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_frame = int(elapsed * self.video_fps)
        if total_frames > 0:
            target_frame = target_frame % total_frames

        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, v_frame = self.video_cap.read()
        if not ret or v_frame is None:
            return

        rgb_v = cv2.cvtColor(v_frame, cv2.COLOR_BGR2RGB)
        pil_v = Image.fromarray(rgb_v)
        ctk_v = ctk.CTkImage(light_image=pil_v, dark_image=pil_v, size=(610, 410))
        self.ref_video_label.configure(image=ctk_v, text="")
        self.ref_video_label.image = ctk_v

    def _draw_dancer_pictogram(self, cx, cy, move_name, color):
        if move_name in self.custom_move_icons:
            self.canvas.create_image(cx, cy, image=self.custom_move_icons[move_name])
            return

        self.canvas.create_oval(cx - 7, cy - 31, cx + 7, cy - 17, fill=color, outline="")
        self.canvas.create_line(cx, cy - 17, cx, cy + 8, fill=color, width=4, capstyle="round")
        self.canvas.create_line(cx, cy + 8, cx - 10, cy + 27, fill=color, width=3, capstyle="round")
        self.canvas.create_line(cx, cy + 8, cx + 10, cy + 27, fill=color, width=3, capstyle="round")

        shoulder_y = cy - 12
        if move_name == "CROWN_REACH":
            self.canvas.create_line(cx, shoulder_y, cx - 15, cy - 35, fill=color, width=4, capstyle="round")
            self.canvas.create_line(cx, shoulder_y, cx + 15, cy - 35, fill=color, width=4, capstyle="round")
        elif move_name == "EGYPTIAN_FRAME":
            self.canvas.create_line(cx, shoulder_y, cx - 18, shoulder_y - 4, fill=color, width=4, capstyle="round")
            self.canvas.create_line(cx, shoulder_y, cx + 22, shoulder_y - 14, fill=color, width=4, capstyle="round")
        elif move_name == "SHOULDER_POP_L":
            self.canvas.create_line(cx, shoulder_y, cx - 14, cy + 4, fill=color, width=4, capstyle="round")
            self.canvas.create_line(cx, shoulder_y, cx + 24, shoulder_y - 4, fill=color, width=4, capstyle="round")
        elif move_name == "SHOULDER_POP_R":
            self.canvas.create_line(cx, shoulder_y, cx - 24, shoulder_y - 4, fill=color, width=4, capstyle="round")
            self.canvas.create_line(cx, shoulder_y, cx + 14, cy + 4, fill=color, width=4, capstyle="round")
        elif move_name == "GROOVE_LOCK":
            self.canvas.create_line(cx, shoulder_y, cx - 18, shoulder_y, fill=color, width=4, capstyle="round")
            self.canvas.create_line(cx, shoulder_y, cx + 18, shoulder_y, fill=color, width=4, capstyle="round")

    def _draw_rhythm_timeline(self, elapsed=0.0):
        self.canvas.delete("all")
        cw = max(self.canvas.winfo_width(), 1200)

        self.canvas.create_line(45, 68, cw - 30, 68, fill="#222b4d", width=4)

        events = self._get_upcoming_and_active_moves(elapsed) if self.is_active else []
        any_active_now = any(active for _, _, active in events)

        zx1, zy1, zx2, zy2 = 42, 10, 178, 126
        if any_active_now:
            self.canvas.create_rectangle(
                zx1 - 4, zy1 - 4, zx2 + 4, zy2 + 4, outline="#39ff14", width=3
            )
            self.canvas.create_rectangle(
                zx1, zy1, zx2, zy2, fill="#0d4722", outline="#39ff14", width=4
            )
            self.canvas.create_text(
                (zx1 + zx2) // 2,
                114,
                text="DANCE NOW!",
                fill="#7dff8a",
                font=("Arial", 10, "bold"),
            )
        else:
            self.canvas.create_rectangle(
                zx1, zy1, zx2, zy2, fill="#131930", outline="#00bbf9", width=3
            )
            self.canvas.create_text(
                (zx1 + zx2) // 2,
                114,
                text="HIT ZONE",
                fill="#00bbf9",
                font=("Arial", 10, "bold"),
            )

        if not self.is_active:
            self.canvas.create_text(
                cw // 2,
                68,
                text="Press START DANCE — moves slide across the bottom and light up GREEN when active!",
                fill="#7aa2f7",
                font=("Arial", 13, "bold"),
            )
            return

        for timestamp, move, is_active_now in events:
            time_until_hit = timestamp - elapsed
            if -0.4 <= time_until_hit <= 4.5:
                card_x = 52 if is_active_now else 52 + (time_until_hit * 245)
                if 45 <= card_x <= cw - 135:
                    w = 128
                    if is_active_now:
                        fill_col = "#15803d"
                        outline_col = "#39ff14"
                        fig_col = "#ffffff"
                        txt_col = "#dcfce7"
                        bw = 4
                    else:
                        fill_col = "#1b2240"
                        outline_col = "#4f65b8"
                        fig_col = "#00f5d4"
                        txt_col = "#e0e6ff"
                        bw = 2

                    self.canvas.create_rectangle(
                        card_x, 16, card_x + w, 112,
                        fill=fill_col, outline=outline_col, width=bw
                    )
                    self._draw_dancer_pictogram(card_x + (w // 2), 54, move, fig_col)
                    self.canvas.create_text(
                        card_x + (w // 2),
                        99,
                        text=move.replace("_", " "),
                        fill=txt_col,
                        font=("Arial", 8, "bold"),
                    )

    def _schedule_gui_update(self):
        if self.is_active:
            elapsed = self.get_elapsed_time()
            self._update_reference_video_frame(elapsed)
            self._draw_rhythm_timeline(elapsed)

            current_move = self.get_current_target_move()
            if current_move:
                self.target_pill.configure(
                    text=f"MOVE: {current_move.replace('_', ' ')}",
                    fg_color="#14532d",
                    text_color="#39ff14",
                )
            else:
                self.target_pill.configure(
                    text="MOVE: GET READY",
                    fg_color="#1c2340",
                    text_color="#7aa2f7",
                )

            if not self.frame_queue.empty():
                try:
                    result, frame = self.frame_queue.get_nowait()
                    raw_status = str(result.get("status", "")).upper().strip()
                    feedback = result.get("feedback_text") or raw_status

                    if current_move is not None and raw_status in ("PERFECT", "GOOD", "MISS"):
                        move_key = (
                            f"{current_move}_{int(elapsed // self.active_window_duration)}"
                        )

                        if raw_status == "PERFECT":
                            self.tier_badge.configure(text="PERFECT!", text_color="#39ff14")
                            self.status_label.configure(text=feedback, text_color="#39ff14")
                            if move_key != self.last_scored_window:
                                self.score += 100
                                self.combo += 1
                                self.max_combo = max(self.max_combo, self.combo)
                                self.last_scored_window = move_key
                                play_perfect_sound()

                        elif raw_status == "GOOD":
                            self.tier_badge.configure(text="GOOD!", text_color="#00f5d4")
                            self.status_label.configure(text=feedback, text_color="#00f5d4")
                            if move_key != self.last_scored_window:
                                self.score += 50
                                self.combo += 1
                                self.max_combo = max(self.max_combo, self.combo)
                                self.last_scored_window = move_key
                                play_okay_sound()

                        elif raw_status == "MISS":
                            self.tier_badge.configure(text="MISS", text_color="#ff4d6d")
                            self.status_label.configure(text=feedback, text_color="#ff4d6d")
                            if move_key != self.last_scored_window:
                                self.combo = 0
                                self.last_scored_window = move_key
                                play_bad_sound()
                    else:
                        self.tier_badge.configure(text="")
                        self.status_label.configure(
                            text="WATCH THE TRACK — GREEN MEANS GO!", text_color="#c0caf5"
                        )

                    self.score_label.configure(
                        text=f"SCORE: {self.score}   |   COMBO: {self.combo}x"
                    )

                    cv2.putText(
                        frame,
                        f"SCORE: {self.score}",
                        (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.85,
                        (0, 245, 212),
                        2,
                    )
                    cv2.putText(
                        frame,
                        f"COMBO: {self.combo}x",
                        (20, 125),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.85,
                        (57, 255, 20),
                        2,
                    )

                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb_frame)
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img, dark_image=pil_img, size=(610, 410)
                    )

                    self.video_label.configure(image=ctk_img, text="")
                    self.video_label.image = ctk_img
                except queue.Empty:
                    pass
                except Exception as e:
                    print(f"[GUI Update Error] {e}", flush=True)
        else:
            self._draw_rhythm_timeline(0.0)

        self.after(20, self._schedule_gui_update)

    def on_closing(self):
        self._stop_game()
        if hasattr(self, "engine") and self.engine:
            try:
                self.engine.close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()