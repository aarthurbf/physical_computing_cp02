"""
smart_gym_cp02.py — Smart Gym | Checkpoint 02
Disciplina: Physical Computing (IoT & IoB) — FIAP
Funcionalidades:
  • Banco de dados SQLite (alunos + log_acessos)
  • Leitura de RFID via serial (Arduino/ESP32)
  • Interface gráfica Tkinter (painel da estação de treino)
  • Monitoramento de pose com MediaPipe (contagem de repetições)
  • Thread separada para não travar a UI durante leitura do sensor / câmera
"""

import os
import time
import sqlite3
import threading
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

DB_PATH     = os.path.join(os.path.dirname(__file__), "..", "db", "smart_gym.db")
MODEL_PATH  = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker_full.task")
SERIAL_PORT = "COM5"          # ← Ajustar conforme porta do Arduino
BAUD_RATE   = 9600

# Estados possíveis da estação
ESTADO_AGUARDANDO = "AGUARDANDO_LOGIN"
ESTADO_TREINO     = "TREINO_ATIVO"
ESTADO_CONCLUIDO  = "TREINO_CONCLUIDO"

# Paleta de cores
COR_BG       = "#0d0d0d"
COR_PAINEL   = "#1a1a1a"
COR_DESTAQUE = "#e91e8c"
COR_VERDE    = "#00e676"
COR_AMARELO  = "#ffd740"
COR_TEXTO    = "#ffffff"
COR_CINZA    = "#888888"
COR_AZUL     = "#00e5ff"

class BancoDados:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def buscar_aluno_por_uid(self, uid: str):
        """Retorna dict do aluno ou None se não encontrado."""
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, nome, exercicio, repeticoes FROM alunos WHERE uid_rfid = ?",
            (uid,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "nome": row[1], "exercicio": row[2], "repeticoes": row[3]}
        return None

    def registrar_acesso(self, aluno_id: int, uid: str) -> int:
        """Cria registro no log_acessos e retorna o id do log."""
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO log_acessos (aluno_id, uid_rfid) VALUES (?, ?)",
            (aluno_id, uid)
        )
        log_id = cur.lastrowid
        conn.commit()
        conn.close()
        return log_id

    def finalizar_acesso(self, log_id: int, reps_feitas: int, concluido: bool):
        """Atualiza o log com repetições realizadas e status de conclusão."""
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE log_acessos SET reps_feitas=?, concluido=? WHERE id=?",
            (reps_feitas, int(concluido), log_id)
        )
        conn.commit()
        conn.close()

    def contar_treinos(self, aluno_id: int) -> int:
        """Conta total de treinos já realizados pelo aluno."""
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM log_acessos WHERE aluno_id=? AND concluido=1",
            (aluno_id,)
        )
        total = cur.fetchone()[0]
        conn.close()
        return total

class LeitorRFID:
    def __init__(self, porta: str, baud: int):
        self.porta = porta
        self.baud  = baud
        self.ser   = None
        self.ativo = False

    def conectar(self) -> bool:
        try:
            import serial
            self.ser   = serial.Serial(self.porta, self.baud, timeout=0.1)
            self.ativo = True
            print(f"[RFID] Arduino conectado em {self.porta}")
            return True
        except Exception as e:
            print(f"[RFID] Sem conexão ({e}) — modo teclado ativo")
            return False

    def ler_uid(self) -> str | None:
        """Retorna UID lido ou None. Não bloqueante."""
        if not self.ativo or not self.ser:
            return None
        try:
            if self.ser.in_waiting > 0:
                linha = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if "UID:" in linha:
                    return linha.split("UID:")[1].strip().upper()
        except Exception:
            pass
        return None

    def fechar(self):
        if self.ser:
            self.ser.close()

class MotorPose:
    def __init__(self, model_path: str):
        self.detector   = None
        self.disponivel = False
        self._carregar(model_path)

    def _carregar(self, model_path):
        if not os.path.exists(model_path):
            print(f"[POSE] Modelo não encontrado: {model_path}")
            return
        try:
            base_options = python.BaseOptions(model_asset_path=model_path)
            options      = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO
            )
            self.detector   = vision.PoseLandmarker.create_from_options(options)
            self.disponivel = True
            print("[POSE] MediaPipe carregado.")
        except Exception as e:
            print(f"[POSE] Erro ao carregar MediaPipe: {e}")

    def processar_frame(self, frame_bgr, timestamp_ms: int):
        """Retorna (angulo, frame_anotado) ou (None, frame_original)."""
        if not self.disponivel:
            return None, frame_bgr

        rgb    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect_for_video(mp_img, timestamp_ms)

        h, w, _ = frame_bgr.shape
        angulo  = None

        if result.pose_landmarks:
            marcos = result.pose_landmarks[0]
            ombro  = (int(marcos[11].x * w), int(marcos[11].y * h))
            cotove = (int(marcos[13].x * w), int(marcos[13].y * h))
            pulso  = (int(marcos[15].x * w), int(marcos[15].y * h))

            angulo = _calcular_angulo(ombro, cotove, pulso)

            # Desenha esqueleto
            cv2.line(frame_bgr, ombro, cotove, (255, 255, 255), 2)
            cv2.line(frame_bgr, cotove, pulso,  (255, 255, 255), 2)
            for pt in [ombro, cotove, pulso]:
                cv2.circle(frame_bgr, pt, 8, (0, 0, 255), -1)

            # Exibe ângulo
            cv2.putText(frame_bgr, f"{int(angulo)}°",
                        (cotove[0] + 15, cotove[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        return angulo, frame_bgr


def _calcular_angulo(a, b, c) -> float:
    a, b, c = np.array(a), np.array(b), np.array(c)
    rad = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    ang = abs(rad * 180.0 / np.pi)
    if ang > 180:
        ang = 360 - ang
    return ang

class SmartGymApp:
    def __init__(self, root: tk.Tk):
        self.root  = root
        self.root.title("Smart Gym — Estação de Treino Inteligente")
        self.root.configure(bg=COR_BG)
        self.root.geometry("1100x700")
        self.root.resizable(False, False)

        # Componentes
        self.db        = BancoDados(DB_PATH)
        self.rfid      = LeitorRFID(SERIAL_PORT, BAUD_RATE)
        self.pose      = MotorPose(MODEL_PATH)
        self.cap       = None

        # Estado da aplicação
        self.estado        = ESTADO_AGUARDANDO
        self.perfil_ativo  = None
        self.log_id        = None
        self.contador_reps = 0
        self.estagio       = ""
        self.total_treinos = 0
        self._ts_inicio    = 0

        self.rfid.conectar()
        self._build_ui()
        self._iniciar_camera()
        self._loop_rfid()
        self._loop_camera()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=COR_DESTAQUE, height=60)
        header.pack(fill=tk.X)

        tk.Label(header, text="⚡ SMART GYM", font=("Helvetica", 22, "bold"),
                 bg=COR_DESTAQUE, fg=COR_TEXTO).pack(side=tk.LEFT, padx=20)

        self.lbl_hora = tk.Label(header, text="", font=("Helvetica", 13),
                                  bg=COR_DESTAQUE, fg=COR_TEXTO)
        self.lbl_hora.pack(side=tk.RIGHT, padx=20)
        self._atualizar_hora()

        corpo = tk.Frame(self.root, bg=COR_BG)
        corpo.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        painel_esq = tk.Frame(corpo, bg=COR_PAINEL, width=320, bd=0,
                               highlightthickness=1, highlightbackground=COR_DESTAQUE)
        painel_esq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        painel_esq.pack_propagate(False)
        self._build_painel_info(painel_esq)

        painel_cam = tk.Frame(corpo, bg=COR_PAINEL, bd=0,
                               highlightthickness=1, highlightbackground="#333333")
        painel_cam.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_painel_camera(painel_cam)

        rodape = tk.Frame(self.root, bg="#111111", height=30)
        rodape.pack(fill=tk.X)
        tk.Label(rodape,
                 text="[S] Entrar como Convidado    [Q] Sair    [R] Resetar estação",
                 font=("Courier", 10), bg="#111111", fg=COR_CINZA).pack()

        # Atalhos de teclado
        self.root.bind("<KeyPress-s>", lambda e: self._login_convidado())
        self.root.bind("<KeyPress-S>", lambda e: self._login_convidado())
        self.root.bind("<KeyPress-q>", lambda e: self._sair())
        self.root.bind("<KeyPress-Q>", lambda e: self._sair())
        self.root.bind("<KeyPress-r>", lambda e: self._resetar())
        self.root.bind("<KeyPress-R>", lambda e: self._resetar())

    def _build_painel_info(self, parent):
        pad = dict(padx=18, pady=6)

        # Status badge
        tk.Label(parent, text="STATUS DA ESTAÇÃO", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack(anchor="w", **pad)

        self.frm_status = tk.Frame(parent, bg=COR_PAINEL)
        self.frm_status.pack(fill=tk.X, padx=18, pady=4)

        self.canvas_status = tk.Canvas(self.frm_status, width=12, height=12,
                                        bg=COR_PAINEL, highlightthickness=0)
        self.canvas_status.pack(side=tk.LEFT)
        self._dot = self.canvas_status.create_oval(1, 1, 11, 11, fill=COR_CINZA)

        self.lbl_status = tk.Label(self.frm_status,
                                    text="Aguardando Login",
                                    font=("Helvetica", 12, "bold"),
                                    bg=COR_PAINEL, fg=COR_CINZA)
        self.lbl_status.pack(side=tk.LEFT, padx=8)

        self._separador(parent)

        # Avatar do aluno
        self.lbl_avatar = tk.Label(parent, text="👤", font=("Helvetica", 48),
                                    bg=COR_PAINEL, fg=COR_CINZA)
        self.lbl_avatar.pack(pady=(12, 0))

        # Nome do aluno
        self.lbl_boas_vindas = tk.Label(parent,
                                         text="Aproxime o cartão\nou pressione [S]",
                                         font=("Helvetica", 14),
                                         bg=COR_PAINEL, fg=COR_CINZA,
                                         justify=tk.CENTER)
        self.lbl_boas_vindas.pack(pady=6)

        self._separador(parent)

        # Exercício
        tk.Label(parent, text="EXERCÍCIO", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack(anchor="w", **pad)
        self.lbl_exercicio = tk.Label(parent, text="—",
                                       font=("Helvetica", 16, "bold"),
                                       bg=COR_PAINEL, fg=COR_AZUL)
        self.lbl_exercicio.pack(anchor="w", padx=18)

        self._separador(parent)

        # Contadores
        frame_reps = tk.Frame(parent, bg=COR_PAINEL)
        frame_reps.pack(fill=tk.X, padx=18, pady=8)

        # Repetições feitas
        frm_l = tk.Frame(frame_reps, bg=COR_PAINEL)
        frm_l.pack(side=tk.LEFT, expand=True)
        tk.Label(frm_l, text="REPS", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack()
        self.lbl_reps = tk.Label(frm_l, text="0",
                                  font=("Helvetica", 40, "bold"),
                                  bg=COR_PAINEL, fg=COR_VERDE)
        self.lbl_reps.pack()

        # Meta
        frm_r = tk.Frame(frame_reps, bg=COR_PAINEL)
        frm_r.pack(side=tk.LEFT, expand=True)
        tk.Label(frm_r, text="META", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack()
        self.lbl_meta = tk.Label(frm_r, text="—",
                                  font=("Helvetica", 40, "bold"),
                                  bg=COR_PAINEL, fg=COR_CINZA)
        self.lbl_meta.pack()

        self._separador(parent)

        # Barra de progresso
        tk.Label(parent, text="PROGRESSO", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack(anchor="w", **pad)
        self.progress_bg = tk.Canvas(parent, height=18, bg="#333333",
                                      highlightthickness=0)
        self.progress_bg.pack(fill=tk.X, padx=18, pady=(0, 8))
        self.progress_fill = self.progress_bg.create_rectangle(
            0, 0, 0, 18, fill=COR_DESTAQUE, outline=""
        )

        self._separador(parent)

        # Treinos realizados
        tk.Label(parent, text="TREINOS CONCLUÍDOS", font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack(anchor="w", **pad)
        self.lbl_total = tk.Label(parent, text="—",
                                   font=("Helvetica", 22, "bold"),
                                   bg=COR_PAINEL, fg=COR_AMARELO)
        self.lbl_total.pack(anchor="w", padx=18)

        # Mensagem de feedback
        self.lbl_feedback = tk.Label(parent, text="",
                                      font=("Helvetica", 11, "italic"),
                                      bg=COR_PAINEL, fg=COR_AMARELO,
                                      wraplength=280, justify=tk.CENTER)
        self.lbl_feedback.pack(pady=8, padx=12)

    def _build_painel_camera(self, parent):
        tk.Label(parent, text="MONITORAMENTO — MEDIAPIPE",
                 font=("Helvetica", 9, "bold"),
                 bg=COR_PAINEL, fg=COR_CINZA).pack(anchor="nw", padx=12, pady=(8, 4))

        self.lbl_cam = tk.Label(parent, bg="#000000")
        self.lbl_cam.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _separador(self, parent):
        tk.Frame(parent, bg="#333333", height=1).pack(fill=tk.X, padx=12, pady=4)

    def _iniciar_camera(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("[CAM] Câmera não disponível.")

    def _loop_camera(self):
        """Atualiza o feed da câmera a ~30 fps sem bloquear a UI."""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.flip(frame, 1)

                if self.estado == ESTADO_TREINO:
                    ts_ms  = int((time.time() - self._ts_inicio) * 1000)
                    angulo, frame = self.pose.processar_frame(frame, ts_ms)
                    self._processar_angulo(angulo)

                elif self.estado == ESTADO_AGUARDANDO:
                    h, w = frame.shape[:2]
                    cv2.putText(frame, "APROXIME O CARTAO",
                                (w//2 - 160, h//2 - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                    cv2.putText(frame, "ou pressione [S]",
                                (w//2 - 120, h//2 + 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)

                # Converte para Tkinter
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb = cv2.resize(frame_rgb, (740, 520))
                from PIL import Image, ImageTk
                img = ImageTk.PhotoImage(Image.fromarray(frame_rgb))
                self.lbl_cam.configure(image=img)
                self.lbl_cam.image = img

        self.root.after(33, self._loop_camera)   # ~30 fps

    def _loop_rfid(self):
        """Verifica RFID a cada 200ms em background (não bloqueia UI)."""
        if self.estado == ESTADO_AGUARDANDO:
            uid = self.rfid.ler_uid()
            if uid:
                self._processar_uid(uid)
        self.root.after(200, self._loop_rfid)

    def _processar_uid(self, uid: str):
        aluno = self.db.buscar_aluno_por_uid(uid)
        if aluno:
            self._ativar_treino(aluno, uid)
        else:
            self._set_feedback(f"UID não cadastrado:\n{uid}", COR_AMARELO)
            print(f"[RFID] UID não encontrado: {uid}")

    def _ativar_treino(self, aluno: dict, uid: str):
        self.perfil_ativo  = aluno
        self.contador_reps = 0
        self.estagio       = ""
        self.log_id        = self.db.registrar_acesso(aluno["id"], uid)
        self.total_treinos = self.db.contar_treinos(aluno["id"])
        self.estado        = ESTADO_TREINO
        self._ts_inicio    = time.time()

        # Atualiza UI
        self.lbl_avatar.configure(text="🏋️", fg=COR_DESTAQUE)
        self.lbl_boas_vindas.configure(
            text=f"Bem-vindo,\n{aluno['nome']}!", fg=COR_TEXTO
        )
        self.lbl_exercicio.configure(text=aluno["exercicio"])
        self.lbl_meta.configure(text=str(aluno["repeticoes"]), fg=COR_TEXTO)
        self.lbl_total.configure(text=str(self.total_treinos))
        self._set_status("Treino Ativo", COR_VERDE)
        self._set_feedback("Posicione-se e comece!", COR_VERDE)
        self._atualizar_reps(0)

        print(f"[GYM] Login: {aluno['nome']} | {aluno['exercicio']} x{aluno['repeticoes']}")

    def _processar_angulo(self, angulo):
        if angulo is None:
            return
        meta = self.perfil_ativo["repeticoes"]

        # Lógica rosca/flexão
        if angulo > 160:
            self.estagio = "descida"
        if angulo < 35 and self.estagio == "descida":
            self.estagio       = "subida"
            self.contador_reps += 1
            self._atualizar_reps(self.contador_reps)

            if self.contador_reps >= meta:
                self._concluir_treino()

    def _concluir_treino(self):
        self.estado = ESTADO_CONCLUIDO
        self.db.finalizar_acesso(self.log_id, self.contador_reps, concluido=True)
        self.total_treinos += 1
        self.lbl_total.configure(text=str(self.total_treinos))
        self._set_status("Treino Concluído ✓", COR_VERDE)
        self._set_feedback("🎉 Parabéns! Meta atingida!\nDescanse 60–90 segundos.", COR_VERDE)
        self.lbl_avatar.configure(text="🏆", fg=COR_VERDE)
        print(f"[GYM] Treino concluído: {self.perfil_ativo['nome']} | "
              f"{self.contador_reps} reps | log_id={self.log_id}")
        # Auto-reset após 8 s
        self.root.after(8000, self._resetar)

    def _resetar(self):
        if self.log_id and self.estado != ESTADO_CONCLUIDO:
            self.db.finalizar_acesso(self.log_id, self.contador_reps, concluido=False)

        self.estado        = ESTADO_AGUARDANDO
        self.perfil_ativo  = None
        self.log_id        = None
        self.contador_reps = 0
        self.estagio       = ""

        self.lbl_avatar.configure(text="👤", fg=COR_CINZA)
        self.lbl_boas_vindas.configure(
            text="Aproxime o cartão\nou pressione [S]", fg=COR_CINZA
        )
        self.lbl_exercicio.configure(text="—")
        self.lbl_reps.configure(text="0", fg=COR_VERDE)
        self.lbl_meta.configure(text="—", fg=COR_CINZA)
        self.lbl_total.configure(text="—")
        self._set_status("Aguardando Login", COR_CINZA)
        self._set_feedback("", COR_CINZA)
        self._atualizar_barra(0, 1)
        print("[GYM] Estação resetada. Aguardando próximo aluno.")

    def _login_convidado(self):
        if self.estado == ESTADO_AGUARDANDO:
            aluno = self.db.buscar_aluno_por_uid("GUEST:000000")
            if aluno:
                self._ativar_treino(aluno, "GUEST:000000")

    def _atualizar_reps(self, reps: int):
        meta = self.perfil_ativo["repeticoes"] if self.perfil_ativo else 1
        self.lbl_reps.configure(text=str(reps))
        cor = COR_VERDE if reps < meta else COR_DESTAQUE
        self.lbl_reps.configure(fg=cor)
        self._atualizar_barra(reps, meta)

    def _atualizar_barra(self, atual: int, total: int):
        self.progress_bg.update_idletasks()
        largura = self.progress_bg.winfo_width()
        if total > 0:
            pct = min(atual / total, 1.0)
        else:
            pct = 0
        self.progress_bg.coords(self.progress_fill, 0, 0, int(largura * pct), 18)

    def _set_status(self, texto: str, cor: str):
        self.lbl_status.configure(text=texto, fg=cor)
        self.canvas_status.itemconfig(self._dot, fill=cor)

    def _set_feedback(self, texto: str, cor: str):
        self.lbl_feedback.configure(text=texto, fg=cor)

    def _atualizar_hora(self):
        agora = datetime.now().strftime("%H:%M:%S  |  %d/%m/%Y")
        self.lbl_hora.configure(text=agora)
        self.root.after(1000, self._atualizar_hora)

    def _sair(self):
        if self.cap:
            self.cap.release()
        self.rfid.fechar()
        self.root.destroy()

if __name__ == "__main__":
    # Garante que o banco existe antes de abrir a UI
    if not os.path.exists(DB_PATH):
        print("[BOOT] Banco não encontrado — execute db/setup_db.py primeiro.")
    else:
        root = tk.Tk()
        app  = SmartGymApp(root)
        root.protocol("WM_DELETE_WINDOW", app._sair)
        root.mainloop()
