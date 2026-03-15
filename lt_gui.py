import sys
import os
import shutil
import subprocess
import threading
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, 
                             QGridLayout, QGroupBox, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont

# --- 资源释放逻辑 ---
def get_lt_path():
    """ 检查并释放 lt.exe 到当前程序运行目录 """
    if hasattr(sys, 'frozen'):
        current_dir = os.path.dirname(sys.executable)
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    
    target_lt = os.path.join(current_dir, "lt.exe")

    if hasattr(sys, '_MEIPASS'):
        source_lt = os.path.join(sys._MEIPASS, "lt.exe")
        if not os.path.exists(target_lt):
            try:
                shutil.copy2(source_lt, target_lt)
            except Exception as e:
                print(f"释放文件失败: {e}")
    
    return target_lt

# --- 进程管理类 ---
class ProcessWorker(QObject):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None

    def run(self):
        try:
            # shell=False 配合列表格式 cmd 是最稳妥的，0x08000000 隐藏黑窗口
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True, 
                shell=False, 
                creationflags=0x08000000
            )
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self.log_signal.emit(line.strip())
        except Exception as e:
            self.log_signal.emit(f"启动失败: {str(e)}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        if self.process:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], creationflags=0x08000000)

# --- 主界面 ---
class LocaltunnelPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Localtunnel 控制面板")
        self.resize(650, 800)
        self.config_file = "lt_config.json"
        self.worker = None
        self.init_ui()
        self.load_config()
        self.apply_style()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. 核心配置 (保留全部参数)
        core_group = QGroupBox("核心配置")
        grid = QGridLayout()
        self.edit_port = self.add_row(grid, "本地端口 (-p):", "8000", 0)
        self.edit_subdomain = self.add_row(grid, "请求子域名 (-s):", "", 1)
        self.edit_host = self.add_row(grid, "中转服务器 (-h):", "https://localtunnel.me", 2)
        self.edit_local_host = self.add_row(grid, "代理主机 (-l):", "localhost", 3)
        core_group.setLayout(grid)
        main_layout.addWidget(core_group)

        # 2. HTTPS & 安全设置 (保留全部参数)
        secure_group = QGroupBox("HTTPS & 安全设置")
        s_grid = QGridLayout()
        self.cb_https = QCheckBox("开启本地 HTTPS (--local-https)")
        self.cb_insecure = QCheckBox("忽略证书检查 (--allow-invalid-cert)")
        self.edit_cert = self.add_row(s_grid, "证书路径 (.pem):", "", 1)
        self.edit_key = self.add_row(s_grid, "私钥路径 (.key):", "", 2)
        self.edit_ca = self.add_row(s_grid, "CA 路径:", "", 3)
        s_grid.addWidget(self.cb_https, 0, 0)
        s_grid.addWidget(self.cb_insecure, 0, 1)
        secure_group.setLayout(s_grid)
        main_layout.addWidget(secure_group)

        # 3. 运行选项
        opt_layout = QHBoxLayout()
        self.cb_open = QCheckBox("自动打开浏览器 (-o)")
        self.cb_open.setChecked(True)
        self.cb_print = QCheckBox("打印详细日志 (--print-requests)")
        opt_layout.addWidget(self.cb_open)
        opt_layout.addWidget(self.cb_print)
        main_layout.addLayout(opt_layout)

        # 4. 控制按钮
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开启隧道")
        self.btn_stop = QPushButton("🛑 停止隧道")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start_tunnel)
        self.btn_stop.clicked.connect(self.stop_tunnel)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        main_layout.addLayout(btn_layout)

        # 5. 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        main_layout.addWidget(self.log_display)

    def add_row(self, layout, label_text, default, row):
        layout.addWidget(QLabel(label_text), row, 0)
        edit = QLineEdit(default)
        layout.addWidget(edit, row, 1)
        return edit

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QGroupBox { font-weight: bold; border: 1px solid #dcdde1; margin-top: 10px; padding: 10px; }
            QPushButton { padding: 10px; font-weight: bold; }
            QPushButton#start { background-color: #44bd32; color: white; border-radius: 4px; }
            QPushButton#stop { background-color: #c23616; color: white; border-radius: 4px; }
            QTextEdit { background-color: #2f3640; color: #f5f6fa; font-family: 'Consolas'; }
        """)
        self.btn_start.setObjectName("start")
        self.btn_stop.setObjectName("stop")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    c = json.load(f)
                    self.edit_port.setText(c.get('port', '8000'))
                    self.edit_subdomain.setText(c.get('sub', ''))
                    self.edit_host.setText(c.get('host', 'https://localtunnel.me'))
                    self.edit_local_host.setText(c.get('lhost', 'localhost'))
            except: pass

    def save_config(self):
        config = {
            'port': self.edit_port.text(),
            'sub': self.edit_subdomain.text(),
            'host': self.edit_host.text(),
            'lhost': self.edit_local_host.text()
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)

    def start_tunnel(self):
        self.save_config()
        lt_exe = get_lt_path()
        
        if not os.path.exists(lt_exe):
            QMessageBox.critical(self, "错误", f"未找到 lt.exe\n路径: {lt_exe}")
            return

        # 核心修复：直接传递路径，不加多余引号
        cmd = [lt_exe, "--port", self.edit_port.text()]
        
        if self.edit_subdomain.text(): cmd.extend(["--subdomain", self.edit_subdomain.text()])
        if self.edit_host.text(): cmd.extend(["--host", self.edit_host.text()])
        if self.edit_local_host.text(): cmd.extend(["--local-host", self.edit_local_host.text()])
        if self.cb_https.isChecked(): cmd.append("--local-https")
        if self.cb_insecure.isChecked(): cmd.append("--allow-invalid-cert")
        if self.edit_cert.text(): cmd.extend(["--local-cert", self.edit_cert.text()])
        if self.edit_key.text(): cmd.extend(["--local-key", self.edit_key.text()])
        if self.edit_ca.text(): cmd.extend(["--local-ca", self.edit_ca.text()])
        if self.cb_open.isChecked(): cmd.append("--open")
        if self.cb_print.isChecked(): cmd.append("--print-requests")

        self.log_display.clear()
        self.log_display.append("<b style='color:white;'>[系统] 正在启动隧道...</b>")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.thread = threading.Thread(target=self.run_worker, args=(cmd,), daemon=True)
        self.thread.start()

    def run_worker(self, cmd):
        self.worker = ProcessWorker(cmd)
        self.worker.log_signal.connect(self.log_display.append)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.run()

    def on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_display.append("<b style='color:#ff5252;'>[系统] 隧道已关闭</b>")

    def stop_tunnel(self):
        if self.worker:
            self.worker.stop()

    def closeEvent(self, event):
        self.stop_tunnel()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LocaltunnelPro()
    window.show()
    sys.exit(app.exec_())