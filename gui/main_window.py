"""主窗口：编排所有组件，串联 导入→OCR→编辑规则→预览→批量执行 全流程。

聊天记录截图附加能力：
- 头像替换（手动框选 / 自动检测圆形头像），支持仅当前图 / 所有图同位置
- 快捷替换（封装全局 contains 规则，用于批量改名/改时间）
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import config_loader
import template_store
from avatar_editor import AvatarEditor
from batch_processor import BatchProcessor
from image_editor import ImageEditor
from models import AvatarReplace, AvatarTemplate, ReplaceRule, TextBox, TextStyle
from ocr_engine import OcrEngine
from style_detector import StyleDetector

import auth
import db
from gui.admin_panel_dialog import AdminPanelDialog
from gui.avatar_dialog import AvatarDialog
from gui.image_canvas import ImageCanvas
from gui.image_manager_dialog import ImageManagerDialog
from gui.login_dialog import LoginDialog
from gui.preview_dialog import PreviewDialog
from gui.records_manager_dialog import RecordsManagerDialog
from gui.results_manager_dialog import ResultsManagerDialog
from gui.rules_table_model import RulesTableModel
from gui.style_panel import StylePanel, _FONT_CHOICES


def bgr_to_qimage(img_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888).copy()


class _OcrWorker(QThread):
    """单图/多图 OCR 子线程，避免阻塞 UI。"""

    one_done = Signal(str, list)  # filename, list[TextBox]
    log = Signal(str)
    all_done = Signal()

    def __init__(self, engine: OcrEngine, image_paths: list[str]):
        super().__init__()
        self._engine = engine
        self._paths = image_paths

    def run(self):
        for p in self._paths:
            try:
                img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    self.log.emit(f"[失败] 无法读取 {os.path.basename(p)}")
                    continue
                boxes = self._engine.recognize_array(img)
                self.one_done.emit(os.path.basename(p), boxes)
                self.log.emit(f"[OCR] {os.path.basename(p)}：识别到 {len(boxes)} 个文字框")
            except Exception as e:
                self.log.emit(f"[OCR失败] {os.path.basename(p)}：{e}")
        self.all_done.emit()


class _SaveTemplateDialog(QDialog):
    """保存头像操作为模板：用户输入模板名。"""

    def __init__(self, op: AvatarReplace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("保存为头像模板")
        self.resize(380, 180)
        self._op = op

        form = QFormLayout(self)
        self._name = QLineEdit()
        self._name.setPlaceholderText("如：微信聊天头像、抖音评论头像")
        self._name.setFocus()
        form.addRow("模板名称:", self._name)

        x, y, w, h = op.rect
        info = QLabel(
            f"位置: ({x}, {y})  尺寸: {w}×{h}  形状: {op.shape}"
        )
        info.setStyleSheet("color:#666;")
        form.addRow("预览:", info)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("保存模板")
        cancel = QPushButton("取消")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)

    def get_name(self) -> str:
        return self._name.text().strip()


class _AvatarTemplateDialog(QDialog):
    """头像模板管理对话框：列表 + 多选批量加载/删除/重命名/导出/导入。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("头像模板库")
        self.resize(560, 460)
        self._templates: list[AvatarTemplate] = []
        self._load_requested = False
        self._load_target_path = ""
        self._load_target_names: list[str] = []

        layout = QVBoxLayout(self)

        tip = QLabel(
            "模板保存头像的位置和形状，下次使用时只需更换头像图片路径即可复用。\n"
            "支持多选：按住 Ctrl 点击选择多个模板，批量加载应用到同一张图。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666;")
        layout.addWidget(tip)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.itemDoubleClicked.connect(self._on_load)
        layout.addWidget(self._list, 1)

        # 计数标签
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#888;")
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._count_lbl)

        btn_row = QHBoxLayout()
        b_load = QPushButton("批量加载并更换头像图")
        b_rename = QPushButton("重命名")
        b_del = QPushButton("删除")
        b_export = QPushButton("导出")
        b_import = QPushButton("导入")
        b_close = QPushButton("关闭")
        b_load.clicked.connect(self._on_load)
        b_rename.clicked.connect(self._on_rename)
        b_del.clicked.connect(self._on_delete)
        b_export.clicked.connect(self._on_export)
        b_import.clicked.connect(self._on_import)
        b_close.clicked.connect(self.reject)
        btn_row.addWidget(b_load)
        btn_row.addWidget(b_rename)
        btn_row.addWidget(b_del)
        btn_row.addStretch()
        btn_row.addWidget(b_export)
        btn_row.addWidget(b_import)
        btn_row.addWidget(b_close)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self._templates = template_store.list_templates()
        self._list.clear()
        for t in self._templates:
            x, y, w, h = t.rect
            item = QListWidgetItem(
                f"📌 {t.name}  [{t.shape}]  ({x},{y},{w},{h})  "
                f"{t.created_at or ''}"
            )
            item.setData(Qt.UserRole, t.name)
            self._list.addItem(item)
        self._on_selection_changed()

    def _on_selection_changed(self):
        selected = len(self._list.selectedItems())
        total = self._list.count()
        self._count_lbl.setText(f"已选 {selected} / {total} 个模板")

    def _selected_names(self) -> list[str]:
        return [
            item.data(Qt.UserRole)
            for item in self._list.selectedItems()
        ]

    def _on_load(self):
        names = self._selected_names()
        if not names:
            QMessageBox.information(self, "提示", "请先选择至少一个模板")
            return
        # 选择新的头像图片（所有选中模板共用同一张新头像）
        path, _ = QFileDialog.getOpenFileName(
            self, "选择新的头像图片（将应用到所有选中模板）", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self._load_requested = True
        self._load_target_path = path
        self._load_target_names = names
        self.accept()

    def _on_rename(self):
        names = self._selected_names()
        if len(names) != 1:
            QMessageBox.information(self, "提示", "重命名请只选中一个模板")
            return
        name = names[0]
        new_name, ok = QInputDialog.getText(
            self, "重命名模板", "新名称:", text=name
        )
        if ok and new_name.strip() and new_name.strip() != name:
            template_store.rename_template(name, new_name.strip())
            self._refresh()

    def _on_delete(self):
        names = self._selected_names()
        if not names:
            QMessageBox.information(self, "提示", "请先选择至少一个模板")
            return
        msg = f"删除选中的 {len(names)} 个模板？\n\n"
        msg += "\n".join(f"  · {n}" for n in names[:8])
        if len(names) > 8:
            msg += f"\n  ... 以及另外 {len(names) - 8} 个"
        if QMessageBox.question(
            self, "确认", msg,
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            for n in names:
                template_store.delete_template(n)
            self._refresh()

    def _on_export(self):
        if not self._templates:
            QMessageBox.information(self, "提示", "暂无模板可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出模板", "avatar_templates.json", "JSON (*.json)"
        )
        if path:
            template_store.export_templates(self._templates, path)
            QMessageBox.information(self, "完成", f"已导出 {len(self._templates)} 个模板")

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入模板", "", "JSON (*.json)"
        )
        if path:
            templates = template_store.import_templates(path)
            self._refresh()
            QMessageBox.information(self, "完成", f"导入后共 {len(templates)} 个模板")

    def get_load_result(self) -> tuple[bool, list[str], str]:
        """返回 (是否加载, 模板名列表, 新头像路径)。"""
        if self._load_requested:
            return True, self._load_target_names, self._load_target_path
        return False, [], ""


class _EditBoxDialog(QDialog):
    """双击 bbox 弹出的快捷编辑对话框。"""

    def __init__(self, tb: TextBox, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑文字替换")
        self.resize(420, 340)
        self._cur_color: tuple[int, int, int] = (0, 0, 0)

        form = QFormLayout(self)
        lbl_old = QLabel(tb.text)
        lbl_old.setWordWrap(True)
        lbl_old.setStyleSheet("color:#c0392b;font-weight:bold;")
        form.addRow("原文字:", lbl_old)
        self._new = QLineEdit()
        self._new.setPlaceholderText("输入替换后的新文字")
        form.addRow("新文字:", self._new)

        self._font = QComboBox()
        for name, _ in _FONT_CHOICES:
            self._font.addItem(name)
        form.addRow("字体:", self._font)

        self._size = QSpinBox()
        self._size.setRange(0, 300)
        self._size.setValue(0)
        self._size.setSpecialValueText("自动")
        form.addRow("字号:", self._size)

        self._color_auto = QCheckBox("自动检测")
        self._color_auto.setChecked(True)
        self._color_btn = QPushButton("选择颜色")
        self._color_btn.setEnabled(False)
        form.addRow("颜色:", self._color_auto)
        form.addRow("", self._color_btn)

        self._bold = QCheckBox("加粗")
        form.addRow("加粗:", self._bold)

        btns = QHBoxLayout()
        ok = QPushButton("添加规则")
        cancel = QPushButton("取消")
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self._color_auto.toggled.connect(lambda c: self._color_btn.setEnabled(not c))
        self._color_btn.clicked.connect(self._pick_color)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(*self._cur_color), self, "选择文字颜色")
        if c.isValid():
            self._cur_color = (c.red(), c.green(), c.blue())

    def get_result(self) -> tuple[str, TextStyle]:
        font_val = _FONT_CHOICES[self._font.currentIndex()][1]
        size = self._size.value() or None
        color = None if self._color_auto.isChecked() else self._cur_color
        style = TextStyle(
            font_color=color,
            font_size=size,
            font_path=font_val or None,
            bold=self._bold.isChecked(),
        )
        return self._new.text(), style


class _QuickReplaceDialog(QDialog):
    """快捷替换对话框：封装一条全局 contains 规则（用于批量改名/改时间）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷替换（批量改名/改时间）")
        self.resize(420, 200)

        form = QFormLayout(self)
        self._old = QLineEdit()
        self._old.setPlaceholderText("原文字片段，如 昵称、时间 2026-07-30")
        form.addRow("原文字:", self._old)

        self._new = QLineEdit()
        self._new.setPlaceholderText("替换后的文字")
        form.addRow("新文字:", self._new)

        self._r_contains = QRadioButton("包含匹配（默认，子串替换）")
        self._r_exact = QRadioButton("精确匹配（整框全等）")
        self._r_regex = QRadioButton("正则匹配")
        self._r_contains.setChecked(True)
        g = QButtonGroup(self)
        for r in (self._r_contains, self._r_exact, self._r_regex):
            g.addButton(r)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._r_contains)
        mode_row.addWidget(self._r_exact)
        mode_row.addWidget(self._r_regex)
        mode_row.addStretch()
        wrap = QWidget()
        wrap.setLayout(mode_row)
        form.addRow("匹配方式:", wrap)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("添加全局规则")
        cancel = QPushButton("取消")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)

    def get_result(self) -> tuple[str, str, str]:
        mode = "contains"
        if self._r_exact.isChecked():
            mode = "exact"
        elif self._r_regex.isChecked():
            mode = "regex"
        return self._old.text(), self._new.text(), mode


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("批量图片文字替换工具")
        self.resize(1400, 860)

        # 先登录
        self._user: auth.SessionUser | None = None
        if not self._do_login():
            raise SystemExit(0)

        # 状态
        self._image_paths: list[str] = []
        self._current_index = -1
        self._current_img_bgr: np.ndarray | None = None
        self._ocr_cache: dict[str, list[TextBox]] = {}
        self._ocr: OcrEngine | None = None
        self._editor = ImageEditor()
        self._detector = StyleDetector()
        self._avatar_editor = AvatarEditor()
        self._avatar_ops: list[AvatarReplace] = []
        self._ocr_worker: _OcrWorker | None = None
        self._batch: BatchProcessor | None = None

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._update_user_label()

    # ---------- 登录 / 登出 ----------

    def _do_login(self) -> bool:
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return False
        self._user = dlg.get_user()
        return self._user is not None

    def _on_logout(self):
        if QMessageBox.question(
            self, "确认", "确定要退出登录吗？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        auth.logout()
        self._user = None
        self.hide()
        # 重新拉起登录
        dlg = LoginDialog()
        if dlg.exec() == QDialog.Accepted:
            self._user = dlg.get_user()
            # 清理当前会话状态
            self._image_paths.clear()
            self._list.clear()
            self._ocr_cache.clear()
            self._avatar_ops.clear()
            self._model.set_rules([])
            self._current_index = -1
            self._canvas.set_boxes([])
            self._refresh_avatar_list()
            self._update_user_label()
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            raise SystemExit(0)

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # 左：图片列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("图片列表"))
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.currentRowChanged.connect(self._on_list_changed)
        ll.addWidget(self._list)
        splitter.addWidget(left)

        # 中：画布
        self._canvas = ImageCanvas()
        self._canvas.box_selected.connect(self._on_box_selected)
        self._canvas.box_double_clicked.connect(self._on_box_double_clicked)
        self._canvas.rect_selected.connect(self._on_rect_selected)
        self._canvas.circle_selected.connect(self._on_circle_selected)
        splitter.addWidget(self._canvas)

        # 右：规则表 + 样式面板
        right = QSplitter(Qt.Vertical)
        rules_box = QWidget()
        rl = QVBoxLayout(rules_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("替换规则（双击单元格编辑，图片路径留空=全局规则）"))
        self._model = RulesTableModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        rl.addWidget(self._table)
        btn_row = QHBoxLayout()
        b_add = QPushButton("＋ 添加规则")
        b_del = QPushButton("－ 删除选中")
        b_add.clicked.connect(self._on_add_rule)
        b_del.clicked.connect(self._on_del_rule)
        btn_row.addWidget(b_add)
        btn_row.addWidget(b_del)
        btn_row.addStretch()
        rl.addLayout(btn_row)
        right.addWidget(rules_box)

        # 头像操作列表
        avatar_box = QWidget()
        al = QVBoxLayout(avatar_box)
        al.setContentsMargins(0, 0, 0, 0)
        al.addWidget(QLabel("头像替换操作（范围·形状·位置）"))
        self._avatar_list = QListWidget()
        self._avatar_list.setSelectionMode(QAbstractItemView.SingleSelection)
        al.addWidget(self._avatar_list)
        av_row = QHBoxLayout()
        b_av_del = QPushButton("－ 删除选中")
        b_av_clear = QPushButton("清空")
        b_save_tpl = QPushButton("💾 存为模板")
        b_load_tpl = QPushButton("📂 模板库")
        b_av_del.clicked.connect(self._on_del_avatar_op)
        b_av_clear.clicked.connect(self._on_clear_avatar_ops)
        b_save_tpl.clicked.connect(self._on_save_as_template)
        b_load_tpl.clicked.connect(self._on_open_template_library)
        av_row.addWidget(b_av_del)
        av_row.addWidget(b_av_clear)
        av_row.addStretch()
        av_row.addWidget(b_save_tpl)
        av_row.addWidget(b_load_tpl)
        al.addLayout(av_row)
        right.addWidget(avatar_box)

        self._style_panel = StylePanel()
        self._style_panel.apply_rule.connect(self._on_apply_rule_from_panel)
        right.addWidget(self._style_panel)
        right.setSizes([420, 180, 240])
        splitter.addWidget(right)

        splitter.setSizes([240, 720, 420])
        outer.addWidget(splitter)

        # 状态栏
        self._progress = QProgressBar()
        self._progress.setFixedWidth(260)
        self._progress.setVisible(False)
        self._status_label = QLabel("就绪")
        self._user_label = QLabel("")
        self._user_label.setStyleSheet("color:#2c3e50;padding:0 8px;")
        bar = self.statusBar()
        bar.addPermanentWidget(self._user_label)
        bar.addWidget(self._progress)
        bar.addWidget(self._status_label, 1)

        self.setCentralWidget(central)

    def _update_user_label(self):
        if self._user is None:
            self._user_label.setText("")
            return
        role = "管理员" if self._user.is_admin else "普通用户"
        self._user_label.setText(f"👤 {self._user.username}（{role}）")

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("文件(&F)")
        for text, slot in [
            ("导入图片...", self._on_import),
            ("加载配置...", self._on_load_config),
            ("保存配置...", self._on_save_config),
            ("生成配置模板...", self._on_gen_template),
            ("导入头像操作...", self._on_import_avatar_ops),
            ("导出头像操作...", self._on_export_avatar_ops),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            m_file.addAction(a)

        m_op = mb.addMenu("操作(&O)")
        for text, slot in [
            ("OCR 识别当前", self._on_ocr_current),
            ("OCR 识别全部", self._on_ocr_all),
            ("预览当前", self._on_preview),
            ("批量执行...", self._on_batch),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            m_op.addAction(a)

        m_avatar = mb.addMenu("头像(&A)")
        for text, slot in [
            ("替换头像（手动框选）", self._on_replace_avatar),
            ("自动检测头像", self._on_detect_avatars),
            ("快捷替换（改名/改时间）", self._on_quick_replace),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            m_avatar.addAction(a)

        m_mgr = mb.addMenu("系统管理(&M)")
        for text, slot in [
            ("图片管理", self._on_image_manager),
            ("替换记录管理", self._on_records_manager),
            ("结果管理", self._on_results_manager),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            m_mgr.addAction(a)
        m_mgr.addSeparator()
        a_admin = QAction("管理员面板", self)
        a_admin.triggered.connect(self._on_admin_panel)
        a_admin.setEnabled(self._user is not None and self._user.is_admin)
        m_mgr.addAction(a_admin)

        m_acc = mb.addMenu("账号(&U)")
        a_logout = QAction("退出登录", self)
        a_logout.triggered.connect(self._on_logout)
        m_acc.addAction(a_logout)

        m_help = mb.addMenu("帮助(&H)")
        a = QAction("关于", self)
        a.triggered.connect(self._on_about)
        m_help.addAction(a)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        for text, slot in [
            ("导入图片", self._on_import),
            ("OCR-当前", self._on_ocr_current),
            ("OCR-全部", self._on_ocr_all),
            ("预览", self._on_preview),
            ("批量执行", self._on_batch),
            ("替换头像", self._on_replace_avatar),
            ("自动检测头像", self._on_detect_avatars),
            ("快捷替换", self._on_quick_replace),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            tb.addAction(a)
        self._act_stop = QAction("停止", self)
        self._act_stop.triggered.connect(self._on_stop)
        tb.addAction(self._act_stop)
        self.addToolBar(tb)

    # ---------- 图片导入与显示 ----------

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
        )
        if not paths:
            return
        for p in paths:
            self._image_paths.append(p)
            self._list.addItem(QListWidgetItem(os.path.basename(p)))
            # 持久化到数据库
            if self._user is not None:
                try:
                    size = os.path.getsize(p) if os.path.exists(p) else 0
                    db.add_image(self._user.id, os.path.basename(p), p, size)
                except Exception as e:
                    self._log(f"图片记录保存失败：{e}")
        if self._current_index < 0:
            self._list.setCurrentRow(0)

    def _on_list_changed(self, row: int):
        if row < 0 or row >= len(self._image_paths):
            return
        self._current_index = row
        self._show_image(row)

    def _show_image(self, index: int):
        if not 0 <= index < len(self._image_paths):
            return
        path = self._image_paths[index]
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            self._log(f"无法读取图片：{path}")
            return
        self._current_img_bgr = img
        fname = os.path.basename(path)
        self._style_panel.set_pattern(fname)
        self._style_panel.clear_info()
        # 显示原图 + 应用匹配的头像操作（预览）
        preview_img, _ = self._avatar_editor.apply_ops(img, self._avatar_ops, fname)
        self._canvas.set_image(bgr_to_qimage(preview_img))
        boxes = self._ocr_cache.get(fname, [])
        self._canvas.set_boxes(boxes)

    # ---------- OCR ----------

    def _ensure_ocr(self):
        if self._ocr is None:
            self._log("正在加载 OCR 引擎（首次约 1-2 秒）...")
            self._ocr = OcrEngine()

    def _on_ocr_current(self):
        if self._current_index < 0:
            QMessageBox.information(self, "提示", "请先导入并选中一张图片")
            return
        self._ensure_ocr()
        self._set_busy(True, "OCR 识别中...")
        self._ocr_worker = _OcrWorker(self._ocr, [self._image_paths[self._current_index]])
        self._ocr_worker.one_done.connect(self._on_ocr_one)
        self._ocr_worker.log.connect(self._log)
        self._ocr_worker.all_done.connect(lambda: self._set_busy(False, "就绪"))
        self._ocr_worker.start()

    def _on_ocr_all(self):
        if not self._image_paths:
            QMessageBox.information(self, "提示", "请先导入图片")
            return
        self._ensure_ocr()
        self._set_busy(True, "批量 OCR 中...")
        self._ocr_worker = _OcrWorker(self._ocr, list(self._image_paths))
        self._ocr_worker.one_done.connect(self._on_ocr_one)
        self._ocr_worker.log.connect(self._log)
        self._ocr_worker.all_done.connect(lambda: self._set_busy(False, "就绪"))
        self._ocr_worker.start()

    def _on_ocr_one(self, fname: str, boxes: list[TextBox]):
        self._ocr_cache[fname] = boxes
        if (
            self._current_index >= 0
            and os.path.basename(self._image_paths[self._current_index]) == fname
        ):
            self._canvas.set_boxes(boxes)

    # ---------- 选中 / 双击 bbox ----------

    def _on_box_selected(self, idx: int):
        if idx < 0:
            self._style_panel.clear_info()
            return
        boxes = self._canvas.get_boxes()
        if idx >= len(boxes) or self._current_img_bgr is None:
            return
        tb = boxes[idx]
        detected = self._detector.detect(self._current_img_bgr, tb)
        self._style_panel.show_textbox(tb, detected)

    def _on_box_double_clicked(self, idx: int):
        boxes = self._canvas.get_boxes()
        if idx >= len(boxes):
            return
        tb = boxes[idx]
        dlg = _EditBoxDialog(tb, self)
        if dlg.exec() == QDialog.Accepted:
            new_text, style = dlg.get_result()
            if not new_text:
                return
            rule = ReplaceRule(
                image_pattern=self._current_pattern(),
                match_mode="contains",
                old_text=tb.text,
                new_text=new_text,
                style=style,
            )
            self._model.add_rule(rule)
            self._persist_rule(rule)
            self._log(f"已添加规则：{tb.text!r} → {new_text!r}")

    def _current_pattern(self) -> str:
        if self._current_index >= 0:
            return os.path.basename(self._image_paths[self._current_index])
        return "*"

    # ---------- 规则表 ----------

    def _on_add_rule(self):
        self._model.add_rule()

    def _on_del_rule(self):
        row = self._table.currentIndex().row()
        if row >= 0:
            self._model.remove_rule(row)

    def _on_apply_rule_from_panel(self, rule: ReplaceRule):
        self._model.add_rule(rule)
        self._persist_rule(rule)
        self._log(f"已添加规则：{rule.old_text!r} → {rule.new_text!r}")

    def _persist_rule(self, rule: ReplaceRule) -> None:
        """将替换规则持久化到数据库（替换记录管理）。"""
        if self._user is None:
            return
        try:
            color = (
                f"#{rule.style.font_color[0]:02x}{rule.style.font_color[1]:02x}{rule.style.font_color[2]:02x}"
                if rule.style.font_color is not None
                else None
            )
            db.add_record(
                user_id=self._user.id,
                image_pattern=rule.image_pattern,
                match_mode=rule.match_mode,
                old_text=rule.old_text,
                new_text=rule.new_text,
                font=rule.style.font_path,
                font_size=rule.style.font_size,
                color=color,
                bold=rule.style.bold,
            )
        except Exception as e:
            self._log(f"替换记录保存失败：{e}")

    # ---------- 系统管理对话框 ----------

    def _on_image_manager(self):
        ImageManagerDialog(self).exec()

    def _on_records_manager(self):
        RecordsManagerDialog(self).exec()

    def _on_results_manager(self):
        ResultsManagerDialog(self).exec()

    def _on_admin_panel(self):
        if self._user is None or not self._user.is_admin:
            QMessageBox.warning(self, "提示", "仅管理员可访问")
            return
        AdminPanelDialog(self).exec()

    # ---------- 头像替换 ----------

    def _on_replace_avatar(self):
        if self._current_img_bgr is None or self._current_index < 0:
            QMessageBox.information(self, "提示", "请先导入并选中一张图片")
            return
        self._canvas.set_selection_mode("rect")
        self._log("请在图片上拖拽框选头像区域")

    def _on_rect_selected(self, x: int, y: int, w: int, h: int):
        if self._current_img_bgr is None or self._current_index < 0:
            return
        dlg = AvatarDialog((x, y, w, h), self)
        if dlg.exec() != QDialog.Accepted:
            return
        avatar_path, shape, apply_all = dlg.get_result()
        pattern = "*" if apply_all else self._current_pattern()
        op = AvatarReplace(
            image_pattern=pattern,
            rect=(x, y, w, h),
            avatar_path=avatar_path,
            shape=shape,
        )
        self._avatar_ops.append(op)
        self._refresh_avatar_list()
        # 即时预览：重新显示当前图（会应用所有匹配的 ops）
        self._show_image(self._current_index)
        self._log(
            f"已添加头像操作：{pattern} {shape} ({x},{y},{w},{h}) ← "
            f"{os.path.basename(avatar_path)}"
        )

    def _on_detect_avatars(self):
        if self._current_img_bgr is None or self._current_index < 0:
            QMessageBox.information(self, "提示", "请先导入并选中一张图片")
            return
        h, w = self._current_img_bgr.shape[:2]
        min_r = 15
        max_r = max(20, min(h, w) // 4)
        circles = self._avatar_editor.detect(self._current_img_bgr, min_r, max_r)
        if not circles:
            QMessageBox.information(self, "提示", "未检测到圆形头像，请改用手动框选")
            return
        self._canvas.set_selection_mode("circle")
        self._canvas.show_circles(circles)
        self._log(f"检测到 {len(circles)} 个候选圆，点击选择目标头像")

    def _on_circle_selected(self, x: int, y: int, r: int):
        if self._current_img_bgr is None or self._current_index < 0:
            return
        # 圆 → 外接正方形 rect
        rect = (x - r, y - r, 2 * r, 2 * r)
        self._canvas.set_selection_mode("normal")
        self._canvas.clear_avatar_overlays()
        self._on_rect_selected(*rect)

    def _on_quick_replace(self):
        dlg = _QuickReplaceDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        old_text, new_text, mode = dlg.get_result()
        if not old_text:
            return
        rule = ReplaceRule(
            image_pattern="*",
            match_mode=mode,
            old_text=old_text,
            new_text=new_text,
            style=TextStyle(),
        )
        self._model.add_rule(rule)
        self._persist_rule(rule)
        self._log(f"已添加全局规则：{old_text!r} → {new_text!r}（{mode}）")

    def _on_del_avatar_op(self):
        row = self._avatar_list.currentRow()
        if 0 <= row < len(self._avatar_ops):
            del self._avatar_ops[row]
            self._refresh_avatar_list()
            if self._current_index >= 0:
                self._show_image(self._current_index)

    def _on_clear_avatar_ops(self):
        if not self._avatar_ops:
            return
        if QMessageBox.question(
            self,
            "确认",
            f"清空全部 {len(self._avatar_ops)} 条头像操作？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._avatar_ops.clear()
        self._refresh_avatar_list()
        if self._current_index >= 0:
            self._show_image(self._current_index)

    def _refresh_avatar_list(self):
        self._avatar_list.clear()
        for i, op in enumerate(self._avatar_ops):
            scope = "全局" if op.is_global() else op.image_pattern
            x, y, w, h = op.rect
            av_name = os.path.basename(op.avatar_path) or "(空)"
            text = f"[{i}] {scope} · {op.shape} · ({x},{y},{w},{h}) ← {av_name}"
            self._avatar_list.addItem(QListWidgetItem(text))

    # ---------- 头像模板管理 ----------

    def _on_save_as_template(self):
        row = self._avatar_list.currentRow()
        if row < 0 or row >= len(self._avatar_ops):
            QMessageBox.information(self, "提示", "请先在头像操作列表中选中一项")
            return
        op = self._avatar_ops[row]
        dlg = _SaveTemplateDialog(op, self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.get_name()
        if not name:
            QMessageBox.warning(self, "提示", "模板名不能为空")
            return
        tmpl = AvatarTemplate(
            name=name,
            rect=op.rect,
            shape=op.shape,
        )
        template_store.save_template(tmpl)
        self._log(f"已保存模板：{name}（位置 {op.rect}，形状 {op.shape}）")

    def _on_open_template_library(self):
        dlg = _AvatarTemplateDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        loaded, tmpl_names, av_path = dlg.get_load_result()
        if not loaded:
            return
        templates = template_store.list_templates()
        name_map = {t.name: t for t in templates}
        applied = 0
        missing = []
        for tmpl_name in tmpl_names:
            tmpl = name_map.get(tmpl_name)
            if tmpl is None:
                missing.append(tmpl_name)
                continue
            op = AvatarReplace(
                image_pattern="*",
                rect=tmpl.rect,
                avatar_path=av_path,
                shape=tmpl.shape,
            )
            self._avatar_ops.append(op)
            applied += 1
        self._refresh_avatar_list()
        if self._current_index >= 0:
            self._show_image(self._current_index)
        msg = f"已加载 {applied} 个模板，共用头像 {os.path.basename(av_path)}"
        if missing:
            msg += f"\n\n跳过不存在的模板：\n" + "\n".join(f"  · {n}" for n in missing)
        self._log(msg.split("\n")[0])
        if missing:
            QMessageBox.warning(self, "部分模板不存在", msg)

    # ---------- 头像操作持久化 ----------

    def _on_import_avatar_ops(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入头像操作", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ops = self._avatar_ops_from_json(data)
            self._avatar_ops.extend(ops)
            self._refresh_avatar_list()
            if self._current_index >= 0:
                self._show_image(self._current_index)
            self._log(f"已导入 {len(ops)} 条头像操作：{path}")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _on_export_avatar_ops(self):
        if not self._avatar_ops:
            QMessageBox.information(self, "提示", "暂无头像操作可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出头像操作", "avatar_ops.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = self._avatar_ops_to_json(self._avatar_ops)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"已导出 {len(self._avatar_ops)} 条头像操作：{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    @staticmethod
    def _avatar_ops_to_json(ops: list[AvatarReplace]) -> list[dict]:
        return [
            {
                "image_pattern": op.image_pattern,
                "rect": list(op.rect),
                "avatar_path": op.avatar_path,
                "shape": op.shape,
            }
            for op in ops
        ]

    @staticmethod
    def _avatar_ops_from_json(data) -> list[AvatarReplace]:
        if not isinstance(data, list):
            raise ValueError("JSON 顶层应为数组")
        ops: list[AvatarReplace] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            rect = item.get("rect") or [0, 0, 0, 0]
            if len(rect) != 4:
                raise ValueError(f"第 {i + 1} 条 rect 字段需为 4 元组")
            ops.append(
                AvatarReplace(
                    image_pattern=str(item.get("image_pattern", "*")),
                    rect=(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])),
                    avatar_path=str(item.get("avatar_path", "")),
                    shape=str(item.get("shape", "circle")),
                )
            )
        return ops

    # ---------- 配置 ----------

    def _on_load_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载配置", "", "Excel/CSV (*.xlsx *.csv)"
        )
        if not path:
            return
        try:
            rules = config_loader.load_rules(path)
            self._model.set_rules(rules)
            self._log(f"已加载 {len(rules)} 条规则：{path}")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", str(e))

    def _on_save_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存配置", "config.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            config_loader.save_rules(self._model.get_rules(), path)
            self._log(f"已保存 {len(self._model.get_rules())} 条规则：{path}")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_gen_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "生成配置模板", "config_template.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            config_loader.generate_template(path)
            self._log(f"已生成模板：{path}")
            QMessageBox.information(self, "完成", f"模板已生成：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    # ---------- 预览 ----------

    def _on_preview(self):
        if self._current_img_bgr is None or self._current_index < 0:
            QMessageBox.information(self, "提示", "请先导入并选中一张图片")
            return
        rules = self._model.get_rules()
        if not rules and not self._avatar_ops:
            QMessageBox.information(self, "提示", "尚无有效替换规则或头像操作")
            return
        boxes = self._canvas.get_boxes()
        fname = os.path.basename(self._image_paths[self._current_index])
        try:
            # 先应用头像替换，再做文字替换（与批量流程一致）
            base_img, av_count = self._avatar_editor.apply_ops(
                self._current_img_bgr, self._avatar_ops, fname
            )
            if rules:
                out, count = self._editor.replace(
                    base_img, boxes, rules, image_filename=fname
                )
            else:
                out, count = base_img, 0
            dlg = PreviewDialog(self)
            dlg.set_images(
                bgr_to_qimage(self._current_img_bgr), bgr_to_qimage(out)
            )
            self._log(f"预览：{fname} 头像 {av_count} 处，文字替换 {count} 处")
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "预览失败", str(e))

    # ---------- 批量执行 ----------

    def _on_batch(self):
        if not self._image_paths:
            QMessageBox.information(self, "提示", "请先导入图片")
            return
        rules = self._model.get_rules()
        if not rules and not self._avatar_ops:
            QMessageBox.warning(self, "提示", "无有效替换规则或头像操作，请先添加")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not out_dir:
            return
        self._ensure_ocr()
        self._batch = BatchProcessor(
            self._image_paths,
            rules,
            out_dir,
            ocr_engine=self._ocr,
            editor=self._editor,
            avatar_ops=list(self._avatar_ops),
            avatar_editor=self._avatar_editor,
        )
        self._batch.progress.connect(self._on_batch_progress)
        self._batch.log.connect(self._log)
        self._batch.finished_all.connect(self._on_batch_finished)
        self._set_busy(True, "批量处理中...")
        self._progress.setVisible(True)
        self._batch.start()

    def _on_batch_progress(self, cur: int, total: int, fname: str):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(cur)
        self._status_label.setText(f"处理 {cur}/{total}：{fname}")

    def _on_batch_finished(self, results: list):
        self._set_busy(False, "就绪")
        self._progress.setVisible(False)
        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        # 持久化结果到数据库
        if self._user is not None:
            # 构建 filename -> image_id 映射
            img_map = {}
            for r in db.list_images(self._user.id):
                img_map[r["filename"]] = r["id"]
            for r in results:
                fname = os.path.basename(r.image_path)
                db.add_result(
                    user_id=self._user.id,
                    image_id=img_map.get(fname),
                    image_filename=fname,
                    output_path=r.output_path,
                    success=r.success,
                    replaced_count=r.replaced_count,
                    avatar_count=r.avatar_count,
                    error=r.error,
                )
        msg = f"批量完成：成功 {ok} 张，失败 {fail} 张"
        if fail:
            errs = "\n".join(
                f"· {os.path.basename(r.image_path)}：{r.error}"
                for r in results
                if not r.success
            )
            msg += f"\n\n失败详情：\n{errs}"
        QMessageBox.information(self, "批量完成", msg)

    def _on_stop(self):
        if self._batch is not None and self._batch.isRunning():
            self._batch.cancel()
            self._log("已请求停止，将在当前图片处理后退出")
        elif self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._ocr_worker.requestInterruption()
            self._log("已请求停止 OCR")

    # ---------- 辅助 ----------

    def _set_busy(self, busy: bool, status: str = ""):
        self._status_label.setText(status or ("就绪" if not busy else "处理中..."))
        self.setEnabled(not busy) if False else None  # 不整体禁用，允许停止
        self._act_stop.setEnabled(busy)

    def _log(self, msg: str):
        self._status_label.setText(msg)

    def _on_about(self):
        QMessageBox.about(
            self,
            "关于",
            "批量图片文字替换工具\n\n"
            "基于 RapidOCR + OpenCV + Pillow + PySide6\n"
            "支持中英混合 OCR 识别、自动匹配原文字样式重绘、Excel/CSV 批量配置。\n\n"
            "流程：导入图片 → OCR 识别 → 编辑替换规则 → 预览 → 批量执行",
        )
