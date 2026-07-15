from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import requests
import serial
from serial.tools import list_ports
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QParallelAnimationGroup,
    QThread,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

SERVER_URL = os.getenv("AKFES_SERVER_URL", "http://127.0.0.1:5000").rstrip("/")
APP_DIR = Path(__file__).resolve().parent
SESSION_FILE = APP_DIR / ".session.json"


@dataclass
class SessionState:
    token: str = ""
    license_expires_at: Optional[int] = None


class ApiWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, action: str, **kwargs):
        super().__init__()
        self.action = action
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            if self.action == "health":
                response = requests.get(f"{SERVER_URL}/health", timeout=5)
                response.raise_for_status()
                self.finished.emit(response.json() if response.content else {"ok": True})
                return

            if self.action == "login":
                response = requests.post(
                    f"{SERVER_URL}/auth/login",
                    json={"license_key": self.kwargs["license_key"]},
                    timeout=10,
                )
                payload = response.json() if response.content else {}
                if not response.ok:
                    raise RuntimeError(payload.get("error", "로그인에 실패했습니다."))
                self.finished.emit(payload)
                return

            if self.action == "process":
                file_path = Path(self.kwargs["file_path"])
                with file_path.open("rb") as handle:
                    response = requests.post(
                        f"{SERVER_URL}/process",
                        headers={"Authorization": f"Bearer {self.kwargs['token']}"},
                        data={"mode": self.kwargs["mode"], "password": self.kwargs["password"]},
                        files={"file": (file_path.name, handle)},
                        timeout=300,
                    )
                if not response.ok:
                    try:
                        message = response.json().get("error", "파일 처리에 실패했습니다.")
                    except Exception:
                        message = "파일 처리에 실패했습니다."
                    raise RuntimeError(message)

                disposition = response.headers.get("Content-Disposition", "")
                filename = self._extract_filename(disposition) or "result.bin"
                output_path = Path(self.kwargs["output_dir"]) / filename
                output_path.write_bytes(response.content)
                self.finished.emit({"output_path": str(output_path), "filename": filename})
                return

            raise RuntimeError("지원하지 않는 작업입니다.")
        except Exception as exc:
            self.failed.emit(str(exc))

    @staticmethod
    def _extract_filename(disposition: str) -> str:
        if "filename*=UTF-8''" in disposition:
            return unquote(disposition.split("filename*=UTF-8''", 1)[1].split(";", 1)[0])
        if "filename=" in disposition:
            return disposition.split("filename=", 1)[1].strip().strip('"')
        return ""


class SerialWorker(QObject):
    line_received = Signal(str)
    connected = Signal(str)
    failed = Signal(str)
    disconnected = Signal()

    def __init__(self, port_name: str):
        super().__init__()
        self.port_name = port_name
        self._running = True
        self.serial: Optional[serial.Serial] = None

    def run(self) -> None:
        try:
            self.serial = serial.Serial(self.port_name, 9600, timeout=0.2)
            time.sleep(1.6)
            self.connected.emit(self.port_name)
            while self._running:
                raw = self.serial.readline()
                if raw:
                    self.line_received.emit(raw.decode("utf-8", errors="replace").strip())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if self.serial and self.serial.is_open:
                self.serial.close()
            self.disconnected.emit()

    def send(self, text: str) -> None:
        if self.serial and self.serial.is_open:
            self.serial.write(text.encode("utf-8"))

    def stop(self) -> None:
        self._running = False


class DropFrame(QFrame):
    file_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropFrame")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 22, 20, 22)
        layout.setSpacing(8)

        self.icon = QLabel("↓")
        self.icon.setObjectName("dropIcon")
        self.title = QLabel("파일을 끌어놓으세요")
        self.title.setObjectName("dropTitle")
        self.subtitle = QLabel("클릭해서 파일을 선택할 수도 있습니다")
        self.subtitle.setObjectName("muted")
        layout.addWidget(self.icon, alignment=Qt.AlignCenter)
        layout.addWidget(self.title, alignment=Qt.AlignCenter)
        layout.addWidget(self.subtitle, alignment=Qt.AlignCenter)

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(self, "파일 선택")
        if path:
            self.file_dropped.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.file_dropped.emit(path)


class TitleBar(QFrame):
    def __init__(self, window: "AKFESWindow"):
        super().__init__()
        self.window = window
        self.drag_position: Optional[QPoint] = None
        self.setObjectName("titleBar")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 6, 0)
        layout.setSpacing(8)

        app_icon = QLabel()
        app_icon.setPixmap(make_app_icon(24).pixmap(24, 24))
        title = QLabel("AKFES")
        title.setObjectName("windowTitle")
        subtitle = QLabel("Native Secure Client")
        subtitle.setObjectName("titleSubtitle")

        layout.addWidget(app_icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()

        self.min_button = self._window_button("—", "minButton")
        self.max_button = self._window_button("□", "maxButton")
        self.close_button = self._window_button("×", "closeButton")
        self.min_button.clicked.connect(window.showMinimized)
        self.max_button.clicked.connect(self.toggle_maximize)
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

    def _window_button(self, text: str, name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setFixedSize(42, 34)
        button.setFocusPolicy(Qt.NoFocus)
        return button

    def toggle_maximize(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
            self.max_button.setText("□")
        else:
            self.window.showMaximized()
            self.max_button.setText("❐")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximize()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window.isMaximized():
            self.drag_position = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_position and event.buttons() & Qt.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
        self.drag_position = None


class AKFESWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AKFES")
        self.setWindowIcon(make_app_icon(64))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(1120, 740)
        self.setMinimumSize(940, 640)

        self.session = self._load_session()
        self.current_file = ""
        self.password = ""
        self.serial_thread: Optional[QThread] = None
        self.serial_worker: Optional[SerialWorker] = None
        self.api_threads: list[QThread] = []
        self._page_animation: Optional[QParallelAnimationGroup] = None

        self._build_ui()
        self._apply_style()
        self._show_page(0, animate=False)
        self._set_session_state(bool(self.session.token))
        QTimer.singleShot(300, self.check_server)

    def _build_ui(self) -> None:
        shell = QFrame()
        shell.setObjectName("windowShell")
        root_layout = QVBoxLayout(shell)
        root_layout.setContentsMargins(1, 1, 1, 1)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)

        body = QWidget()
        body.setObjectName("body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(26, 20, 26, 24)
        body_layout.setSpacing(18)

        self.hero_title = QLabel("안전한 파일 처리를 시작합니다")
        self.hero_title.setObjectName("heroTitle")
        self.hero_desc = QLabel("라이선스 인증부터 파일 처리까지 한 단계씩 진행하세요.")
        self.hero_desc.setObjectName("heroDescription")

        hero_row = QHBoxLayout()
        hero_text = QVBoxLayout()
        hero_text.setSpacing(3)
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_desc)
        hero_row.addLayout(hero_text)
        hero_row.addStretch()

        self.server_badge = QLabel("● 서버 확인 중")
        self.arduino_badge = QLabel("● Arduino 미연결")
        self.session_badge = QLabel("● 세션 미인증")
        for badge in (self.server_badge, self.arduino_badge, self.session_badge):
            badge.setObjectName("badge")
            hero_row.addWidget(badge)
        body_layout.addLayout(hero_row)

        self.step_bar = QFrame()
        self.step_bar.setObjectName("stepBar")
        step_layout = QHBoxLayout(self.step_bar)
        step_layout.setContentsMargins(14, 10, 14, 10)
        step_layout.setSpacing(8)
        self.step_buttons: list[QPushButton] = []
        for index, text in enumerate(("라이선스", "장치 연결", "파일 작업", "결과")):
            button = QPushButton(f"{index + 1}   {text}")
            button.setObjectName("stepButton")
            button.setProperty("state", "idle")
            button.setEnabled(False)
            step_layout.addWidget(button)
            self.step_buttons.append(button)
        body_layout.addWidget(self.step_bar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")
        self.stack.addWidget(self._license_page())
        self.stack.addWidget(self._arduino_page())
        self.stack.addWidget(self._file_page())
        self.stack.addWidget(self._result_page())
        body_layout.addWidget(self.stack, 1)

        root_layout.addWidget(body, 1)
        self.setCentralWidget(shell)

    def _page_shell(self, title: str, description: str, accent: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 95))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(38, 32, 38, 32)
        layout.setSpacing(15)

        accent_label = QLabel(accent)
        accent_label.setObjectName("eyebrow")
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setObjectName("muted")
        layout.addWidget(accent_label)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addSpacing(4)

        outer.addWidget(card, 1)
        return page, layout

    def _license_page(self) -> QWidget:
        page, layout = self._page_shell(
            "라이선스 인증",
            "발급받은 라이선스 키를 입력하면 인증 후 다음 화면으로 이동합니다.",
            "STEP 01 · LICENSE",
        )
        self.license_input = QLineEdit()
        self.license_input.setEchoMode(QLineEdit.Password)
        self.license_input.setPlaceholderText("HCK1.으로 시작하는 라이선스 키")
        self.license_input.returnPressed.connect(self.login)

        self.login_status = QLabel("로그인이 필요합니다.")
        self.login_status.setObjectName("statusPanel")

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.login_btn = QPushButton("인증하고 계속")
        self.login_btn.setObjectName("primary")
        self.login_btn.clicked.connect(self.login)
        button_row.addWidget(self.login_btn)

        layout.addStretch()
        layout.addWidget(self.license_input)
        layout.addWidget(self.login_status)
        layout.addLayout(button_row)
        layout.addStretch()
        return page

    def _arduino_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Arduino 연결",
            "USB로 연결된 Arduino Uno를 선택하세요. 연결이 완료되면 파일 작업 화면으로 이동할 수 있습니다.",
            "STEP 02 · DEVICE",
        )
        content = QHBoxLayout()
        content.setSpacing(16)

        left = QVBoxLayout()
        self.port_list = QListWidget()
        self.port_list.setObjectName("portList")
        self.port_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.port_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.port_list.setMinimumHeight(210)
        left.addWidget(self.port_list)

        row = QHBoxLayout()
        refresh_btn = QPushButton("포트 새로고침")
        refresh_btn.clicked.connect(self.refresh_ports)
        connect_btn = QPushButton("선택한 포트 연결")
        connect_btn.setObjectName("primary")
        connect_btn.clicked.connect(self.connect_serial)
        row.addWidget(refresh_btn)
        row.addWidget(connect_btn)
        left.addLayout(row)

        right = QVBoxLayout()
        self.connection_status = QLabel("연결 대기 중")
        self.connection_status.setObjectName("devicePanel")
        self.connection_status.setWordWrap(True)
        next_btn = QPushButton("파일 작업으로 이동")
        next_btn.setObjectName("primary")
        next_btn.clicked.connect(lambda: self._show_page(2) if self.serial_worker else self._notify("Arduino를 먼저 연결하세요."))
        right.addWidget(self.connection_status, 1)
        right.addWidget(next_btn)

        content.addLayout(left, 3)
        content.addLayout(right, 2)
        layout.addLayout(content, 1)
        self.refresh_ports()
        return page

    def _file_page(self) -> QWidget:
        page, layout = self._page_shell(
            "파일 암호화 및 복호화",
            "파일과 작업 모드를 선택하고 Arduino 키패드로 비밀번호를 입력하세요.",
            "STEP 03 · PROCESS",
        )
        content = QHBoxLayout()
        content.setSpacing(18)

        left = QVBoxLayout()
        self.drop = DropFrame()
        self.drop.file_dropped.connect(self.set_file)
        self.file_label = QLabel("선택된 파일 없음")
        self.file_label.setObjectName("statusPanel")
        self.file_label.setWordWrap(True)
        left.addWidget(self.drop, 1)
        left.addWidget(self.file_label)

        right_panel = QFrame()
        right_panel.setObjectName("sidePanel")
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(20, 20, 20, 20)
        right.setSpacing(14)

        mode_title = QLabel("작업 모드")
        mode_title.setObjectName("sectionTitle")
        self.encrypt_radio = QRadioButton("암호화")
        self.decrypt_radio = QRadioButton("복호화")
        self.encrypt_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.encrypt_radio)
        mode_group.addButton(self.decrypt_radio)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.encrypt_radio)
        mode_row.addWidget(self.decrypt_radio)

        password_title = QLabel("키패드 비밀번호")
        password_title.setObjectName("sectionTitle")
        self.password_label = QLabel("키패드 입력 대기 중")
        self.password_label.setObjectName("password")
        self.password_label.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()

        self.process_btn = QPushButton("파일 처리 실행")
        self.process_btn.setObjectName("primary")
        self.process_btn.clicked.connect(self.process_file)

        right.addWidget(mode_title)
        right.addLayout(mode_row)
        right.addSpacing(8)
        right.addWidget(password_title)
        right.addWidget(self.password_label)
        right.addStretch()
        right.addWidget(self.progress)
        right.addWidget(self.process_btn)

        content.addLayout(left, 3)
        content.addWidget(right_panel, 2)
        layout.addLayout(content, 1)
        return page

    def _result_page(self) -> QWidget:
        page, layout = self._page_shell(
            "작업 완료",
            "처리된 파일의 저장 위치를 확인하세요.",
            "STEP 04 · COMPLETE",
        )
        self.result_label = QLabel("아직 처리된 파일이 없습니다.")
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setObjectName("resultPanel")
        new_btn = QPushButton("새 작업 시작")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self.reset_workflow)
        layout.addStretch()
        layout.addWidget(self.result_label, 1)
        layout.addWidget(new_btn, alignment=Qt.AlignCenter)
        layout.addStretch()
        return page

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            * { font-family: 'Segoe UI', 'Malgun Gothic'; font-size: 14px; }
            QMainWindow { background: transparent; }
            QFrame#windowShell { background: #06101d; border: 1px solid #1b426d; border-radius: 16px; }
            QWidget#body { background: #071321; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }
            QFrame#titleBar { background: #0a1a2d; border-bottom: 1px solid #193858; border-top-left-radius: 16px; border-top-right-radius: 16px; }
            QLabel#windowTitle { color: #f8fbff; font-size: 15px; font-weight: 800; letter-spacing: 1px; }
            QLabel#titleSubtitle { color: #6683a3; font-size: 11px; }
            QPushButton#minButton, QPushButton#maxButton, QPushButton#closeButton { border: 0; background: transparent; color: #a7bed7; font-size: 15px; border-radius: 8px; }
            QPushButton#minButton:hover, QPushButton#maxButton:hover { background: #173250; color: white; }
            QPushButton#closeButton:hover { background: #e5484d; color: white; }

            QLabel#heroTitle { color: #f8fbff; font-size: 24px; font-weight: 800; }
            QLabel#heroDescription { color: #7994b2; }
            QLabel#badge { color: #9fb8d4; background: #0c2036; border: 1px solid #1c456e; border-radius: 13px; padding: 8px 11px; }

            QFrame#stepBar { background: #0a1b2f; border: 1px solid #183b60; border-radius: 16px; }
            QPushButton#stepButton { background: transparent; border: 0; color: #5f7b99; padding: 9px 14px; font-weight: 700; border-radius: 10px; }
            QPushButton#stepButton[state='active'] { color: white; background: #1677ff; }
            QPushButton#stepButton[state='done'] { color: #8ec2ff; background: #0f2c4d; }

            QWidget#page { background: transparent; }
            QFrame#card { background: #0b1b2f; border: 1px solid #1f4a78; border-radius: 24px; }
            QLabel#eyebrow { color: #58a5ff; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
            QLabel#pageTitle { color: #ffffff; font-size: 30px; font-weight: 800; }
            QLabel#muted { color: #829bb7; line-height: 1.5; }
            QLabel#sectionTitle { color: #dfeeff; font-size: 13px; font-weight: 800; }

            QLineEdit { min-height: 48px; color: white; background: #071421; border: 1px solid #285b90; border-radius: 13px; padding: 0 14px; selection-background-color: #1677ff; }
            QLineEdit:focus { border: 2px solid #4a9cff; background: #091a2c; }

            QPushButton { min-height: 42px; color: #dcecff; background: #102944; border: 1px solid #2b5c8c; border-radius: 12px; padding: 0 17px; font-weight: 700; }
            QPushButton:hover { background: #173b62; border-color: #3d79b5; }
            QPushButton:pressed { background: #0d2137; }
            QPushButton#primary { color: white; background: #1677ff; border: 0; }
            QPushButton#primary:hover { background: #338cff; }
            QPushButton#primary:pressed { background: #0d66df; }
            QPushButton:disabled { color: #58718a; background: #0b1e32; border-color: #173750; }

            QLabel#statusPanel, QLabel#devicePanel { color: #cfe6ff; background: #071522; border: 1px solid #204b76; border-radius: 13px; padding: 14px; }
            QLabel#devicePanel { font-size: 16px; min-height: 120px; }
            QLabel#resultPanel { color: #dff2ff; background: #071522; border: 1px solid #245888; border-radius: 18px; padding: 28px; font-size: 17px; }
            QFrame#sidePanel { background: #081827; border: 1px solid #1c4168; border-radius: 18px; }

            QListWidget#portList { color: #d9ebff; background: #071522; border: 1px solid #224f7c; border-radius: 15px; padding: 8px; outline: 0; }
            QListWidget#portList::item { min-height: 42px; border-radius: 10px; padding: 8px 10px; margin: 2px; }
            QListWidget#portList::item:hover { background: #102d4c; }
            QListWidget#portList::item:selected { background: #1677ff; color: white; }

            QFrame#dropFrame { background: #081827; border: 2px dashed #2c669d; border-radius: 18px; min-height: 240px; }
            QFrame#dropFrame:hover { background: #0b2137; border-color: #4b9cff; }
            QFrame#dropFrame[dragging='true'] { background: #0d2d4b; border-color: #71b5ff; }
            QLabel#dropIcon { color: #66adff; font-size: 38px; font-weight: 300; }
            QLabel#dropTitle { color: white; font-size: 18px; font-weight: 800; }

            QLabel#password { color: #92c8ff; background: #050d16; border: 1px solid #2d6ca8; border-radius: 14px; padding: 17px; font-size: 22px; letter-spacing: 5px; }
            QRadioButton { color: #d9eaff; spacing: 8px; }
            QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #4f79a4; background: #081421; }
            QRadioButton::indicator:checked { border: 5px solid #1677ff; background: white; }

            QProgressBar { min-height: 8px; max-height: 8px; background: #071421; border: 0; border-radius: 4px; }
            QProgressBar::chunk { background: #1677ff; border-radius: 4px; }
            QScrollBar { width: 0px; height: 0px; background: transparent; }
        """)

    def _show_page(self, index: int, animate: bool = True) -> None:
        index = max(0, min(3, index))
        old_widget = self.stack.currentWidget()
        new_widget = self.stack.widget(index)
        self.stack.setCurrentIndex(index)

        titles = (
            ("안전한 파일 처리를 시작합니다", "라이선스 키를 인증해 세션을 시작하세요."),
            ("하드웨어 장치를 연결합니다", "Arduino Uno와 연결한 뒤 파일 작업을 진행하세요."),
            ("파일을 안전하게 처리합니다", "암호화 또는 복호화 작업을 선택하세요."),
            ("작업이 완료되었습니다", "처리 결과와 저장 위치를 확인하세요."),
        )
        self.hero_title.setText(titles[index][0])
        self.hero_desc.setText(titles[index][1])

        for i, button in enumerate(self.step_buttons):
            state = "active" if i == index else "done" if i < index else "idle"
            button.setProperty("state", state)
            button.style().unpolish(button)
            button.style().polish(button)

        if not animate or old_widget is new_widget:
            return

        opacity = QGraphicsOpacityEffect(new_widget)
        new_widget.setGraphicsEffect(opacity)
        opacity_anim = QPropertyAnimation(opacity, b"opacity")
        opacity_anim.setDuration(260)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        start = new_widget.pos() + QPoint(18, 0)
        end = new_widget.pos()
        move_anim = QPropertyAnimation(new_widget, b"pos")
        move_anim.setDuration(280)
        move_anim.setStartValue(start)
        move_anim.setEndValue(end)
        move_anim.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(opacity_anim)
        group.addAnimation(move_anim)
        group.finished.connect(lambda: new_widget.setGraphicsEffect(None))
        group.start()
        self._page_animation = group

    def _notify(self, text: str) -> None:
        QMessageBox.information(self, "AKFES", text)

    def _run_api(self, action: str, success, failure=None, **kwargs) -> None:
        thread = QThread(self)
        worker = ApiWorker(action, **kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(success)
        worker.failed.connect(failure or (lambda message: self._notify(message)))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self.api_threads.remove(thread) if thread in self.api_threads else None)
        self.api_threads.append(thread)
        thread.start()

    def check_server(self) -> None:
        self._run_api("health", lambda _: self._set_server_state(True), lambda _: self._set_server_state(False))

    def _set_server_state(self, online: bool) -> None:
        self.server_badge.setText("● 서버 온라인" if online else "● 서버 오프라인")
        self.server_badge.setStyleSheet("color:#67e3aa;" if online else "color:#ff7f91;")

    def _set_session_state(self, active: bool) -> None:
        self.session_badge.setText("● 세션 인증됨" if active else "● 세션 미인증")
        self.session_badge.setStyleSheet("color:#67e3aa;" if active else "color:#ff7f91;")

    def login(self) -> None:
        key = self.license_input.text().strip()
        if not key:
            self._notify("라이선스 키를 입력하세요.")
            return
        self.login_btn.setEnabled(False)
        self.login_status.setText("라이선스 검증 중...")
        self._run_api("login", self._login_success, self._login_failure, license_key=key)

    def _login_success(self, payload: dict) -> None:
        self.login_btn.setEnabled(True)
        self.session.token = payload.get("session_token", "")
        self.session.license_expires_at = payload.get("license_expires_at")
        self._save_session()
        self._set_session_state(True)
        self.login_status.setText("인증이 완료되었습니다.")
        self.license_input.clear()
        QTimer.singleShot(260, lambda: self._show_page(1))

    def _login_failure(self, message: str) -> None:
        self.login_btn.setEnabled(True)
        self.login_status.setText(f"인증 실패: {message}")
        self.session = SessionState()
        self._save_session()
        self._set_session_state(False)

    def refresh_ports(self) -> None:
        self.port_list.clear()
        ports = list(list_ports.comports())
        for port in ports[:5]:
            item = QListWidgetItem(f"{port.device}    {port.description}")
            item.setData(Qt.UserRole, port.device)
            self.port_list.addItem(item)
        if not ports:
            item = QListWidgetItem("사용 가능한 시리얼 포트가 없습니다.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.port_list.addItem(item)

    def connect_serial(self) -> None:
        item = self.port_list.currentItem()
        if not item or not item.data(Qt.UserRole):
            self._notify("연결할 포트를 선택하세요.")
            return
        self.disconnect_serial()
        self.serial_thread = QThread(self)
        self.serial_worker = SerialWorker(item.data(Qt.UserRole))
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_thread.started.connect(self.serial_worker.run)
        self.serial_worker.connected.connect(self._serial_connected)
        self.serial_worker.line_received.connect(self._serial_line)
        self.serial_worker.failed.connect(lambda message: self.connection_status.setText(f"연결 실패: {message}"))
        self.serial_worker.disconnected.connect(self._serial_disconnected)
        self.serial_thread.start()
        self.connection_status.setText("Arduino 연결 중...")

    def _serial_connected(self, port_name: str) -> None:
        self.connection_status.setText(f"{port_name} 연결 완료\nREADY 신호를 기다리는 중입니다.")
        self.arduino_badge.setText("● Arduino 연결됨")
        self.arduino_badge.setStyleSheet("color:#67e3aa;")

    def _serial_line(self, line: str) -> None:
        if "READY" in line:
            self.connection_status.setText("Arduino 준비 완료\n파일 작업을 시작할 수 있습니다.")
            return
        if "KEY:" in line:
            key = line.split("KEY:", 1)[1][:1]
            self._handle_key(key)

    def _handle_key(self, key: str) -> None:
        if key == "#":
            self.process_file()
        elif key == "*":
            self.password = self.password[:-1]
        elif key in "0123456789ABCD" and len(self.password) < 64:
            self.password += key
        self.password_label.setText("•" * len(self.password) if self.password else "키패드 입력 대기 중")

    def disconnect_serial(self) -> None:
        if self.serial_worker:
            self.serial_worker.stop()
        if self.serial_thread:
            self.serial_thread.quit()
            self.serial_thread.wait(800)
        self.serial_worker = None
        self.serial_thread = None

    def _serial_disconnected(self) -> None:
        self.arduino_badge.setText("● Arduino 미연결")
        self.arduino_badge.setStyleSheet("color:#ff7f91;")

    def set_file(self, path: str) -> None:
        file_path = Path(path)
        if not file_path.is_file():
            return
        self.current_file = str(file_path)
        size = file_path.stat().st_size
        size_text = f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
        self.file_label.setText(f"{file_path.name}\n{size_text}")
        self.drop.title.setText("파일 선택 완료")
        self.drop.subtitle.setText(file_path.name)

    def process_file(self) -> None:
        if not self.session.token:
            self._notify("라이선스 인증이 필요합니다.")
            self._show_page(0)
            return
        if not self.serial_worker:
            self._notify("Arduino를 먼저 연결하세요.")
            self._show_page(1)
            return
        if not self.current_file:
            self._notify("파일을 선택하세요.")
            return
        if not self.password:
            self._notify("키패드로 비밀번호를 입력하세요.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "결과 저장 폴더 선택")
        if not output_dir:
            return
        self.progress.show()
        self.process_btn.setEnabled(False)
        mode = "encrypt" if self.encrypt_radio.isChecked() else "decrypt"
        self._run_api(
            "process",
            self._process_success,
            self._process_failure,
            file_path=self.current_file,
            output_dir=output_dir,
            token=self.session.token,
            password=self.password,
            mode=mode,
        )

    def _process_success(self, payload: dict) -> None:
        self.progress.hide()
        self.process_btn.setEnabled(True)
        output_path = payload["output_path"]
        self.result_label.setText(f"처리가 완료되었습니다.\n\n{output_path}")
        if self.serial_worker:
            self.serial_worker.send("SUCCESS\n")
        self.password = ""
        self.password_label.setText("키패드 입력 대기 중")
        self._show_page(3)

    def _process_failure(self, message: str) -> None:
        self.progress.hide()
        self.process_btn.setEnabled(True)
        if self.serial_worker:
            self.serial_worker.send("FAIL\n")
        if any(word in message for word in ("토큰", "인증", "로그인", "만료")):
            self.session = SessionState()
            self._save_session()
            self._set_session_state(False)
            self._show_page(0)
        self._notify(message)

    def reset_workflow(self) -> None:
        self.current_file = ""
        self.password = ""
        self.file_label.setText("선택된 파일 없음")
        self.password_label.setText("키패드 입력 대기 중")
        self.drop.title.setText("파일을 끌어놓으세요")
        self.drop.subtitle.setText("클릭해서 파일을 선택할 수도 있습니다")
        self._show_page(2)

    def _load_session(self) -> SessionState:
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            return SessionState(token=data.get("token", ""), license_expires_at=data.get("license_expires_at"))
        except Exception:
            return SessionState()

    def _save_session(self) -> None:
        try:
            SESSION_FILE.write_text(json.dumps(self.session.__dict__, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self.disconnect_serial()
        event.accept()


def make_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#1677ff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, size * 0.24, size * 0.24)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", int(size * 0.45), QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "A")
    painter.end()
    return QIcon(pixmap)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AKFES")
    app.setOrganizationName("Smarttiger2338")
    app.setWindowIcon(make_app_icon(64))
    window = AKFESWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
