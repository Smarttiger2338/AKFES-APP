from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import serial
from serial.tools import list_ports
from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
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
    QTextEdit,
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
            from urllib.parse import unquote
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
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.title = QLabel("파일을 끌어놓으세요")
        self.title.setObjectName("dropTitle")
        self.subtitle = QLabel("또는 클릭하여 파일 선택")
        self.subtitle.setObjectName("muted")
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
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.file_dropped.emit(path)


class AKFESWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AKFES")
        self.resize(1100, 720)
        self.setMinimumSize(900, 620)

        self.session = self._load_session()
        self.current_file = ""
        self.password = ""
        self.serial_thread: Optional[QThread] = None
        self.serial_worker: Optional[SerialWorker] = None
        self.api_threads: list[QThread] = []

        self._build_ui()
        self._apply_style()
        self._show_page(0, animate=False)
        QTimer.singleShot(300, self.check_server)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 18, 24, 24)
        root_layout.setSpacing(18)

        header = QHBoxLayout()
        brand = QLabel("AKFES")
        brand.setObjectName("brand")
        subtitle = QLabel("Native File Encryption Client")
        subtitle.setObjectName("muted")
        brand_box = QVBoxLayout()
        brand_box.addWidget(brand)
        brand_box.addWidget(subtitle)
        header.addLayout(brand_box)
        header.addStretch()

        self.server_badge = QLabel("서버 확인 중")
        self.arduino_badge = QLabel("Arduino 연결 안 됨")
        self.session_badge = QLabel("세션 미인증")
        for badge in (self.server_badge, self.arduino_badge, self.session_badge):
            badge.setObjectName("badge")
            header.addWidget(badge)
        root_layout.addLayout(header)

        self.step_list = QListWidget()
        self.step_list.setFixedWidth(220)
        self.step_list.setObjectName("stepList")
        for text in ["1  라이선스 인증", "2  Arduino 연결", "3  파일 작업", "4  결과"]:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.step_list.addItem(item)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._license_page())
        self.stack.addWidget(self._arduino_page())
        self.stack.addWidget(self._file_page())
        self.stack.addWidget(self._result_page())

        content = QHBoxLayout()
        content.addWidget(self.step_list)
        content.addWidget(self.stack, 1)
        root_layout.addLayout(content, 1)

        self.setCentralWidget(root)

    def _card(self, title: str, description: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 110))
        frame.setGraphicsEffect(shadow)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(38, 34, 38, 34)
        layout.setSpacing(16)
        h1 = QLabel(title)
        h1.setObjectName("title")
        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        layout.addWidget(h1)
        layout.addWidget(desc)
        return frame, layout

    def _license_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch()
        card, layout = self._card("라이선스 인증", "발급받은 라이선스 키를 입력하여 세션을 시작하세요.")
        self.license_input = QLineEdit()
        self.license_input.setEchoMode(QLineEdit.Password)
        self.license_input.setPlaceholderText("HCK1.으로 시작하는 라이선스 키")
        self.license_input.returnPressed.connect(self.login)
        self.login_status = QLabel("로그인이 필요합니다.")
        self.login_status.setObjectName("status")
        login_btn = QPushButton("인증하고 계속")
        login_btn.setObjectName("primary")
        login_btn.clicked.connect(self.login)
        layout.addWidget(self.license_input)
        layout.addWidget(self.login_status)
        layout.addWidget(login_btn)
        outer.addWidget(card)
        outer.addStretch()
        return page

    def _arduino_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch()
        card, layout = self._card("Arduino 연결", "USB로 연결된 Arduino Uno의 포트를 선택하세요.")
        self.port_list = QListWidget()
        self.port_list.setMinimumHeight(170)
        refresh_btn = QPushButton("포트 새로고침")
        refresh_btn.clicked.connect(self.refresh_ports)
        connect_btn = QPushButton("선택한 포트 연결")
        connect_btn.setObjectName("primary")
        connect_btn.clicked.connect(self.connect_serial)
        self.connection_status = QLabel("연결 대기 중")
        self.connection_status.setObjectName("status")
        next_btn = QPushButton("파일 작업으로 이동")
        next_btn.clicked.connect(lambda: self._show_page(2) if self.serial_worker else self._notify("Arduino를 먼저 연결하세요."))
        layout.addWidget(self.port_list)
        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addWidget(connect_btn)
        layout.addLayout(row)
        layout.addWidget(self.connection_status)
        layout.addWidget(next_btn)
        outer.addWidget(card)
        outer.addStretch()
        self.refresh_ports()
        return page

    def _file_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card("파일 암호화 및 복호화", "파일과 작업 모드를 선택하고 키패드로 비밀번호를 입력하세요.")
        self.drop = DropFrame()
        self.drop.file_dropped.connect(self.set_file)
        self.file_label = QLabel("선택된 파일 없음")
        self.file_label.setObjectName("status")

        mode_row = QHBoxLayout()
        self.encrypt_radio = QRadioButton("암호화")
        self.decrypt_radio = QRadioButton("복호화")
        self.encrypt_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.encrypt_radio)
        mode_group.addButton(self.decrypt_radio)
        mode_row.addWidget(self.encrypt_radio)
        mode_row.addWidget(self.decrypt_radio)
        mode_row.addStretch()

        self.password_label = QLabel("키패드 입력 대기 중")
        self.password_label.setObjectName("password")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.process_btn = QPushButton("파일 처리 실행")
        self.process_btn.setObjectName("primary")
        self.process_btn.clicked.connect(self.process_file)

        layout.addWidget(self.drop)
        layout.addWidget(self.file_label)
        layout.addLayout(mode_row)
        layout.addWidget(self.password_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.process_btn)
        outer.addWidget(card)
        return page

    def _result_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch()
        card, layout = self._card("작업 완료", "처리 결과를 확인하세요.")
        self.result_label = QLabel("아직 처리된 파일이 없습니다.")
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("status")
        new_btn = QPushButton("새 작업 시작")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self.reset_workflow)
        layout.addWidget(self.result_label)
        layout.addWidget(new_btn)
        outer.addWidget(card)
        outer.addStretch()
        return page

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #07111f; color: #eef6ff; font-family: 'Segoe UI'; font-size: 14px; }
            QLabel#brand { font-size: 28px; font-weight: 800; color: white; }
            QLabel#muted { color: #8ea6c3; }
            QLabel#badge { background: #10223c; border: 1px solid #224b78; border-radius: 12px; padding: 8px 12px; color: #bcd8f6; }
            QListWidget#stepList { background: #0b1729; border: 1px solid #1d3a5e; border-radius: 18px; padding: 12px; }
            QListWidget#stepList::item { padding: 15px 12px; margin: 4px; border-radius: 10px; color: #8ea6c3; }
            QListWidget#stepList::item:selected { background: #1167d8; color: white; }
            QFrame#card { background: #0d1c31; border: 1px solid #214a77; border-radius: 24px; }
            QLabel#title { font-size: 30px; font-weight: 800; }
            QLabel#status { background: #081424; border: 1px solid #1f456f; border-radius: 12px; padding: 13px; color: #cfe5fb; }
            QLabel#password { background: #050c16; border: 1px solid #2d65a3; border-radius: 14px; padding: 18px; color: #8bc2ff; font-size: 24px; letter-spacing: 5px; }
            QLineEdit { background: #081424; border: 1px solid #2a5a90; border-radius: 12px; padding: 13px; selection-background-color: #1677ff; }
            QLineEdit:focus { border: 2px solid #2f8cff; }
            QPushButton { background: #132944; border: 1px solid #2d5f96; border-radius: 12px; padding: 12px 18px; font-weight: 700; }
            QPushButton:hover { background: #1a3b62; }
            QPushButton#primary { background: #1677ff; border: none; color: white; }
            QPushButton#primary:hover { background: #2d8bff; }
            QListWidget { background: #081424; border: 1px solid #254f7e; border-radius: 12px; padding: 8px; }
            QFrame#dropFrame { background: #0a182a; border: 2px dashed #2e639d; border-radius: 18px; min-height: 200px; }
            QFrame#dropFrame[dragging='true'] { background: #102b4b; border-color: #58a4ff; }
            QLabel#dropTitle { font-size: 20px; font-weight: 700; }
            QProgressBar { background: #081424; border: 1px solid #234c78; border-radius: 8px; height: 14px; text-align: center; }
            QProgressBar::chunk { background: #1677ff; border-radius: 7px; }
            QRadioButton { spacing: 8px; }
        """)

    def _show_page(self, index: int, animate: bool = True) -> None:
        self.stack.setCurrentIndex(index)
        self.step_list.setCurrentRow(index)
        if animate:
            widget = self.stack.currentWidget()
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(35)
            effect.setColor(QColor(22, 119, 255, 80))
            widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"blurRadius", self)
            anim.setDuration(450)
            anim.setStartValue(55)
            anim.setEndValue(20)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._page_anim = anim

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
        self.server_badge.setText("서버 온라인" if online else "서버 오프라인")
        self.server_badge.setStyleSheet("color:#75e0b0;" if online else "color:#ff8796;")

    def login(self) -> None:
        key = self.license_input.text().strip()
        if not key:
            self._notify("라이선스 키를 입력하세요.")
            return
        self.login_status.setText("라이선스 검증 중...")
        self._run_api("login", self._login_success, self._login_failure, license_key=key)

    def _login_success(self, payload: dict) -> None:
        self.session.token = payload.get("session_token", "")
        self.session.license_expires_at = payload.get("license_expires_at")
        self._save_session()
        self.session_badge.setText("세션 인증됨")
        self.session_badge.setStyleSheet("color:#75e0b0;")
        self.login_status.setText("인증이 완료되었습니다.")
        self.license_input.clear()
        QTimer.singleShot(350, lambda: self._show_page(1))

    def _login_failure(self, message: str) -> None:
        self.login_status.setText(f"인증 실패: {message}")
        self.session = SessionState()
        self._save_session()

    def refresh_ports(self) -> None:
        self.port_list.clear()
        ports = list(list_ports.comports())
        for port in ports:
            item = QListWidgetItem(f"{port.device}  ·  {port.description}")
            item.setData(Qt.UserRole, port.device)
            self.port_list.addItem(item)
        if not ports:
            self.port_list.addItem("사용 가능한 시리얼 포트가 없습니다.")

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
        self.connection_status.setText(f"{port_name} 연결 완료 · READY 대기 중")
        self.arduino_badge.setText("Arduino 연결됨")
        self.arduino_badge.setStyleSheet("color:#75e0b0;")

    def _serial_line(self, line: str) -> None:
        if "READY" in line:
            self.connection_status.setText("Arduino 준비 완료")
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
        self.arduino_badge.setText("Arduino 연결 안 됨")
        self.arduino_badge.setStyleSheet("color:#ff8796;")

    def set_file(self, path: str) -> None:
        file_path = Path(path)
        if not file_path.is_file():
            return
        self.current_file = str(file_path)
        self.file_label.setText(f"{file_path.name} · {file_path.stat().st_size / 1024:.1f} KB")

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
        self.result_label.setText(f"완료되었습니다.\n\n저장 위치: {output_path}")
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
            self._show_page(0)
        self._notify(message)

    def reset_workflow(self) -> None:
        self.current_file = ""
        self.password = ""
        self.file_label.setText("선택된 파일 없음")
        self.password_label.setText("키패드 입력 대기 중")
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AKFES")
    app.setOrganizationName("Smarttiger2338")
    window = AKFESWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
