import sys
import cv2
import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFileDialog,
                               QSpinBox, QProgressBar, QMessageBox, QFrame, QSlider)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont

# --- Shadcn UI 风格定义 ---
SHADCN_STYLE = """
QMainWindow { background-color: #ffffff; }
QFrame#Card { 
    background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; 
}
QLabel#Title { font-size: 14px; font-weight: 600; color: #18181b; }
QLabel#Info { color: #71717a; font-size: 12px; }
QLabel#Badge { 
    background-color: #f4f4f5; color: #18181b; border: 1px solid #e4e4e7;
    border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;
}
QLabel#VideoDisplay { background: #000000; border-radius: 10px; border: 1px solid #e4e4e7; }
QPushButton { 
    background-color: #18181b; color: #ffffff; border-radius: 6px; 
    padding: 8px 16px; font-weight: 500; font-size: 13px;
}
QPushButton:hover { background-color: #27272a; }
QPushButton#Secondary { 
    background-color: #ffffff; color: #18181b; border: 1px solid #e4e4e7; 
}
QPushButton#Secondary:hover { background-color: #f4f4f5; }
QPushButton#Action { background-color: #2563eb; }
QPushButton#Action:hover { background-color: #1d4ed8; }
QProgressBar { 
    border: 1px solid #e4e4e7; background: #f4f4f5; border-radius: 6px; 
    height: 10px; text-align: center; color: transparent;
}
QProgressBar::chunk { background-color: #2563eb; border-radius: 5px; }
QSpinBox { 
    border: 1px solid #e4e4e7; border-radius: 6px; padding: 4px 8px; background: white;
}
"""


class VideoWorker(QThread):
    progress_sig = Signal(int, str)
    finished_sig = Signal(str)

    def __init__(self, v_path, s_dir, gap, start_idx, end_idx):
        super().__init__()
        self.v_path = v_path
        self.s_dir = s_dir
        self.gap = gap
        self.start_idx = start_idx
        self.end_idx = end_idx

    def run(self):
        cap = cv2.VideoCapture(self.v_path)
        if not cap.isOpened():
            self.finished_sig.emit("失败：无法打开视频文件。")
            return

        cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_idx)
        total_range = max(1, self.end_idx - self.start_idx)
        current = self.start_idx
        saved_count = 0

        os.makedirs(self.s_dir, exist_ok=True)

        while current <= self.end_idx:
            ret, frame = cap.read()
            if not ret: break

            if (current - self.start_idx) % self.gap == 0:
                out_name = os.path.join(self.s_dir, f"frame_{current:06d}.jpg")
                success, img_encode = cv2.imencode('.jpg', frame)
                if success:
                    img_encode.tofile(out_name)
                    saved_count += 1

            current += 1
            if current % 10 == 0:
                p = int(((current - self.start_idx) / total_range) * 100)
                self.progress_sig.emit(min(99, p), f"批量处理中: {min(current, self.end_idx)} 帧")

        cap.release()
        self.progress_sig.emit(100, "批量任务已完成")
        self.finished_sig.emit(f"任务成功！共保存 {saved_count} 张图片。")


class FrameFlowPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_path = ""
        self.save_folder = ""
        self.cap = None
        self.fps = 30
        self.initUI()

        self.timer = QTimer()
        self.timer.timeout.connect(self.video_step)

    def initUI(self):
        self.setWindowTitle("FrameFlow Pro - 最终版")
        self.setFixedSize(940, 840)
        self.setStyleSheet(SHADCN_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(25, 25, 25, 25)
        main_lay.setSpacing(15)

        # 1. 预览卡片
        self.display = QLabel("请导入视频文件开始预览")
        self.display.setObjectName("VideoDisplay")
        self.display.setFixedSize(890, 420)
        self.display.setAlignment(Qt.AlignCenter)
        main_lay.addWidget(self.display)

        # 2. 播放与标记控制 (增加捕捉当前帧按钮)
        timeline_card = QFrame();
        timeline_card.setObjectName("Card")
        time_lay = QVBoxLayout(timeline_card)

        slider_row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.on_slider_manual)
        self.lbl_time = QLabel("00:00 / 00:00")
        slider_row.addWidget(self.slider)
        slider_row.addWidget(self.lbl_time)
        time_lay.addLayout(slider_row)

        btn_row = QHBoxLayout()
        self.btn_play = QPushButton("播放/暂停");
        self.btn_play.setObjectName("Secondary")
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_in = QPushButton("标记起点 [");
        self.btn_in.setObjectName("Secondary")
        self.btn_in.clicked.connect(lambda: self.spin_start.setValue(self.slider.value()))

        self.btn_out = QPushButton("标记终点 ]");
        self.btn_out.setObjectName("Secondary")
        self.btn_out.clicked.connect(lambda: self.spin_end.setValue(self.slider.value()))

        # --- 重新加入的功能按钮 ---
        self.btn_snap = QPushButton("捕捉当前帧 📸");
        self.btn_snap.setObjectName("Secondary")
        self.btn_snap.clicked.connect(self.capture_current_frame)

        btn_row.addWidget(self.btn_play)
        btn_row.addSpacing(10)
        btn_row.addWidget(self.btn_in)
        btn_row.addWidget(self.btn_out)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_snap)  # 右侧对齐
        time_lay.addLayout(btn_row)
        main_lay.addWidget(timeline_card)

        # 3. 设置区
        config_row = QHBoxLayout()

        param_card = QFrame();
        param_card.setObjectName("Card")
        param_lay = QVBoxLayout(param_card)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("批量设置", objectName="Title"))
        title_row.addStretch()
        self.lbl_count_badge = QLabel("预计: 0 张")
        self.lbl_count_badge.setObjectName("Badge")
        title_row.addWidget(self.lbl_count_badge)
        param_lay.addLayout(title_row)

        h_set = QHBoxLayout()
        self.spin_start = QSpinBox();
        self.spin_end = QSpinBox()
        self.spin_gap = QSpinBox();
        self.spin_gap.setValue(10);
        self.spin_gap.setRange(1, 9999)

        self.spin_start.valueChanged.connect(self.update_stats)
        self.spin_end.valueChanged.connect(self.update_stats)
        self.spin_gap.valueChanged.connect(self.update_stats)

        h_set.addWidget(QLabel("从"));
        h_set.addWidget(self.spin_start)
        h_set.addWidget(QLabel("至"));
        h_set.addWidget(self.spin_end)
        h_set.addWidget(QLabel("间隔"));
        h_set.addWidget(self.spin_gap)
        param_lay.addLayout(h_set)
        config_row.addWidget(param_card, 3)

        dir_card = QFrame();
        dir_card.setObjectName("Card")
        dir_lay = QVBoxLayout(dir_card)
        dir_lay.addWidget(QLabel("保存路径", objectName="Title"))
        self.lbl_dir = QLabel("未选择")
        self.lbl_dir.setObjectName("Info")
        btn_dir = QPushButton("更改目录");
        btn_dir.setObjectName("Secondary")
        btn_dir.clicked.connect(self.select_folder)
        dir_lay.addWidget(self.lbl_dir);
        dir_lay.addWidget(btn_dir)
        config_row.addWidget(dir_card, 2)

        main_lay.addLayout(config_row)

        # 4. 底部执行
        self.lbl_status = QLabel("系统就绪")
        self.lbl_status.setObjectName("Info")
        main_lay.addWidget(self.lbl_status)
        self.pbar = QProgressBar()
        main_lay.addWidget(self.pbar)

        exec_row = QHBoxLayout()
        btn_imp = QPushButton("导入视频");
        btn_imp.setObjectName("Secondary")
        btn_imp.clicked.connect(self.import_video)
        self.btn_run = QPushButton("开始批量执行");
        self.btn_run.setObjectName("Action")
        self.btn_run.setFixedHeight(45);
        self.btn_run.clicked.connect(self.run_task)
        exec_row.addWidget(btn_imp, 1);
        exec_row.addWidget(self.btn_run, 2)
        main_lay.addLayout(exec_row)

    # --- 功能逻辑 ---
    def import_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择视频")
        if f:
            self.video_path = f
            self.cap = cv2.VideoCapture(f)
            total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.slider.setRange(0, total - 1)
            self.spin_start.setRange(0, total - 1);
            self.spin_end.setRange(0, total - 1)
            self.spin_start.setValue(0);
            self.spin_end.setValue(total - 1)
            self.save_folder = os.path.join(os.path.dirname(f), "frames_output")
            self.lbl_dir.setText(self.save_folder)
            self.update_frame(0)
            self.update_stats()

    def update_stats(self):
        diff = self.spin_end.value() - self.spin_start.value()
        count = max(0, (diff // self.spin_gap.value()) + 1)
        self.lbl_count_badge.setText(f"预计: {count} 张")

    def select_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if d: self.save_folder = d; self.lbl_dir.setText(d)

    def update_frame(self, idx):
        if not self.cap: return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, c = frame.shape
            q_img = QImage(frame.data, w, h, w * c, QImage.Format_RGB888)
            self.display.setPixmap(
                QPixmap.fromImage(q_img).scaled(self.display.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            s = int(idx / self.fps);
            ts = int(self.slider.maximum() / self.fps)
            self.lbl_time.setText(f"{s // 60:02d}:{s % 60:02d} / {ts // 60:02d}:{ts % 60:02d}")

    def on_slider_manual(self, v):
        if not self.timer.isActive(): self.update_frame(v)

    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop(); self.btn_play.setText("播放")
        else:
            self.timer.start(int(1000 / self.fps)); self.btn_play.setText("暂停")

    def video_step(self):
        v = self.slider.value()
        if v < self.slider.maximum():
            self.slider.setValue(v + 1); self.update_frame(v + 1)
        else:
            self.timer.stop(); self.btn_play.setText("播放")

    def capture_current_frame(self):
        """核心修复：单帧捕捉功能"""
        if not self.video_path: return
        os.makedirs(self.save_folder, exist_ok=True)
        idx = self.slider.value()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self.cap.read()
        if ret:
            out_path = os.path.join(self.save_folder, f"snapshot_{idx:06d}.jpg")
            success, img_encode = cv2.imencode('.jpg', frame)
            if success:
                img_encode.tofile(out_path)
                QMessageBox.information(self, "完成", f"快照已保存：\n{out_path}")

    def run_task(self):
        if not self.video_path: return
        self.btn_run.setEnabled(False)
        self.pbar.setValue(0)
        self.worker = VideoWorker(self.video_path, self.save_folder, self.spin_gap.value(), self.spin_start.value(),
                                  self.spin_end.value())
        self.worker.progress_sig.connect(lambda p, m: [self.pbar.setValue(p), self.lbl_status.setText(m)])
        self.worker.finished_sig.connect(
            lambda m: [QMessageBox.information(self, "批量完成", m), self.btn_run.setEnabled(True)])
        self.worker.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = FrameFlowPro();
    win.show()
    sys.exit(app.exec())