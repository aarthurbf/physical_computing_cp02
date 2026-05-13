# 🏋️ Smart Gym — Checkpoint 02
### Physical Computing (IoT & IoB) | FIAP — Engenharia de Software

---

## 👥 Equipe

| Nome | RM |
|---|---|
| *Arthur Bobadilla Franchi* | RM 555056 |
| *Luan Orlandelli Ramos* | RM 554747 |
| *Jorge Luiz* | RM 554418 |

---

## 📌 Sobre o Projeto

Evolução do CP01: agora a estação de treino inteligente conta com **persistência de dados (SQLite)** e uma **interface gráfica completa (Tkinter)**. O sistema identifica o aluno via RFID, exibe boas-vindas com o nome e exercício programado, monitora a pose em tempo real com **MediaPipe** e registra cada acesso em log automático.

### Fluxo completo
```
Aproximação do cartão RFID
        ↓
Consulta no banco SQLite (alunos)
        ↓
Exibe nome + exercício na interface Tkinter
        ↓
Câmera ativa com esqueleto MediaPipe
        ↓
Contagem de repetições em tempo real
        ↓
Registro de log no banco (log_acessos)
        ↓
Parabéns + reset automático da estação
```

---

## 🗄️ Banco de Dados (SQLite)

Arquivo: `db/smart_gym.db`

### Tabela `alunos`
| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador único |
| `nome` | TEXT | Nome do aluno |
| `uid_rfid` | TEXT UNIQUE | UID do cartão RFID |
| `exercicio` | TEXT | Exercício programado |
| `repeticoes` | INTEGER | Meta de repetições |
| `criado_em` | DATETIME | Data de cadastro |

### Tabela `log_acessos`
| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | ID do log |
| `aluno_id` | INTEGER FK | Referência ao aluno |
| `uid_rfid` | TEXT | UID lido no acesso |
| `horario` | DATETIME | Timestamp automático |
| `reps_feitas` | INTEGER | Repetições realizadas na sessão |
| `concluido` | INTEGER | 1 = meta atingida, 0 = parcial |

---

## 🔩 Hardware & Componentes

| Componente | Qtd | Observação |
|---|---|---|
| Arduino Uno / Nano | 1 | Ou ESP32 |
| Módulo RFID RC522 | 1 | Comunicação SPI |
| Cartões/tags RFID (Mifare 1K) | 2+ | UID cadastrado no banco |
| LED Verde | 1 | Feedback de leitura |
| LED Vermelho | 1 | Erro / UID inválido |
| Buzzer passivo | 1 | Feedback sonoro |
| Resistores 220Ω | 2 | Para os LEDs |
| Webcam USB | 1 | Monitoramento de pose |
| Cabo USB | 1 | Comunicação Serial |

---

## 📚 Bibliotecas

### Python
| Biblioteca | Uso |
|---|---|
| `opencv-python` | Captura e processamento de imagem |
| `mediapipe` | Detecção de pose (PoseLandmarker) |
| `numpy` | Cálculo de ângulos |
| `pyserial` | Comunicação serial com Arduino |
| `Pillow` | Exibição de frames no Tkinter |
| `sqlite3` | Banco de dados (nativa) |
| `tkinter` | Interface gráfica (nativa) |

### Arduino
| Biblioteca | Uso |
|---|---|
| `MFRC522` | Comunicação com módulo RFID RC522 |
| `SPI` | Barramento SPI (nativa) |

---

## 🔌 Diagrama de Conexões (RC522 → Arduino Uno)

```
RC522          Arduino Uno
─────────────────────────
SDA    ──────→  D10
SCK    ──────→  D13
MOSI   ──────→  D11
MISO   ──────→  D12
IRQ    ──────→  (não usado)
GND    ──────→  GND
RST    ──────→  D9
3.3V   ──────→  3.3V

LED Verde  ──── 220Ω ──── D7 ──── GND
LED Verm   ──── 220Ω ──── D8 ──── GND
Buzzer     ──────────────  D6 ──── GND
```

> **Atenção:** RC522 opera em 3.3V. Não conecte ao 5V.

---

## ⚙️ Setup e Execução

### 1. Instalar dependências Python
```bash
pip install opencv-python mediapipe numpy pyserial Pillow
```

### 2. Criar e popular o banco de dados
```bash
python db/setup_db.py
```

### 3. Adicionar seu aluno ao banco (opcional)
```python
# No arquivo db/setup_db.py, adicione na lista `alunos`:
("SeuNome", "UID_DO_SEU_CARTAO", "Exercicio", 10)
# Execute novamente: python db/setup_db.py
```

### 4. Configurar porta serial
No arquivo `src/smart_gym_cp02.py`, ajuste a constante:
```python
SERIAL_PORT = "COM5"   # Windows: COM3, COM4... / Linux: /dev/ttyUSB0
```

### 5. Upload do sketch Arduino
- Abra `arduino/Smart_Gym_RFID.ino` na Arduino IDE
- Instale a biblioteca **MFRC522** (Library Manager)
- Selecione a placa e porta corretas → Upload

### 6. Executar o sistema
```bash
python src/smart_gym_cp02.py
```

### Atalhos da interface
| Tecla | Ação |
|---|---|
| `S` | Entrar como Convidado (sem RFID) |
| `R` | Resetar a estação |
| `Q` | Sair do sistema |

---

## 🎬 Vídeo Demonstrativo

> 🔗 [https://youtube.com/shorts/99KwAtavkmg?feature=share]

---

## 📁 Estrutura do Repositório

```
physical_computing_cp02/
├── arduino/
│   └── Smart_Gym_RFID.ino      # Sketch Arduino (RFID RC522)
├── db/
│   ├── setup_db.py             # Cria e popula o banco SQLite
│   └── smart_gym.db            # Banco de dados gerado
├── src/
│   └── smart_gym_cp02.py       # Aplicação principal (Tkinter + MediaPipe)
├── pose_landmarker_full.task   # Modelo MediaPipe (copiar do CP01)
└── README.md
```

---

## 📝 Notas Técnicas

- A interface **não trava** pois usa `root.after()` para polling da câmera e do RFID, respeitando o event loop do Tkinter — sem necessidade de threads manuais.
- O banco é **criado automaticamente** via `setup_db.py` antes da primeira execução.
- O aluno **Convidado** está pré-cadastrado com UID `GUEST:000000` para testes sem hardware.
- O sistema **registra o log** mesmo em treinos incompletos (campo `concluido = 0`).

---

*CP02 — Smart Gym | Physical Computing (IoT & IoB) — FIAP 2026*
