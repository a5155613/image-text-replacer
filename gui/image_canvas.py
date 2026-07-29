"""图片画布：QGraphicsView 显示图片 + 绘制 OCR bbox + 选中/双击/缩放。

附加模式（互斥）：
- "normal"：默认，拖拽平移、点击/双击 bbox
- "rect"：鼠标拖拽画橡皮筋矩形，释放发 rect_selected(x,y,w,h)（原图像素坐标）
- "circle"：显示 detect 返回的圆（半透明蓝），点击选中发 circle_selected(x,y,r)
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from models import TextBox


class ImageCanvas(QGraphicsView):
    box_selected = Signal(int)  # 选中 bbox 索引，-1 表示取消选中
    box_double_clicked = Signal(int)
    rect_selected = Signal(int, int, int, int)  # x, y, w, h（原图像素坐标）
    circle_selected = Signal(int, int, int)  # x, y, r（原图像素坐标）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(
            self.renderHints()
            | QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(40, 40, 40))

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._box_items: list[QGraphicsPolygonItem] = []
        self._text_items: list[QGraphicsTextItem] = []
        self._boxes: list[TextBox] = []
        self._selected_index = -1

        # 头像选择模式相关
        self.mode = "normal"  # "normal" / "rect" / "circle"
        self._rubber_origin: QPointF | None = None
        self._rubber_item: QGraphicsRectItem | None = None
        self._circle_items: list[QGraphicsEllipseItem] = []

    # ---------- 图片与 bbox ----------

    def set_image(self, qimage: QImage):
        self._scene.clear()
        self._pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
        self._scene.addItem(self._pixmap_item)
        self._box_items = []
        self._text_items = []
        self._boxes = []
        self._selected_index = -1
        self._scene.setSceneRect(qimage.rect())
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def set_boxes(self, boxes: list[TextBox]):
        # 清除旧 bbox（保留 pixmap）
        for item in self._box_items + self._text_items:
            self._scene.removeItem(item)
        self._box_items = []
        self._text_items = []
        self._boxes = list(boxes)
        self._selected_index = -1

        label_font = QFont("Microsoft YaHei", 9)
        label_font.setBold(True)
        for i, tb in enumerate(boxes):
            poly = QPolygonF([QPointF(float(p[0]), float(p[1])) for p in tb.polygon])
            item = QGraphicsPolygonItem(poly)
            self._apply_style(item, selected=False)
            item.setData(0, i)
            item.setToolTip(f"[{i}] {tb.text}\n置信度: {tb.score:.1%}")
            self._scene.addItem(item)
            self._box_items.append(item)

            x, y, w, h = tb.bbox_rect
            label = QGraphicsTextItem(tb.text)
            label.setDefaultTextColor(QColor(255, 255, 255))
            label.setFont(label_font)
            label.setPos(x, max(0, y - 18))
            label.setFlag(QGraphicsTextItem.ItemIgnoresTransformations, True)
            self._scene.addItem(label)
            self._text_items.append(label)

    def clear_boxes(self):
        for item in self._box_items + self._text_items:
            self._scene.removeItem(item)
        self._box_items = []
        self._text_items = []
        self._boxes = []
        self._selected_index = -1

    # ---------- 头像选择模式 ----------

    def set_selection_mode(self, mode: str):
        """切换交互模式：normal / rect / circle。"""
        if mode not in ("normal", "rect", "circle"):
            mode = "normal"
        self.mode = mode
        # rect 模式需要自定义鼠标拖拽，禁用 ScrollHandDrag 以免冲突
        self.setDragMode(QGraphicsView.NoDrag if mode == "rect" else QGraphicsView.ScrollHandDrag)
        # 离开 rect 模式时清理未完成的橡皮筋
        if mode != "rect" and self._rubber_item is not None:
            self._scene.removeItem(self._rubber_item)
            self._rubber_item = None
            self._rubber_origin = None
        # 非 circle 模式清掉检测圆
        if mode != "circle":
            self.clear_avatar_overlays()
        self.viewport().setCursor(Qt.CrossCursor if mode == "rect" else Qt.ArrowCursor)

    def show_circles(self, circles: list[tuple[int, int, int]]):
        """显示 detect 返回的圆（半透明蓝），可点击选中。"""
        self.clear_avatar_overlays()
        for x, y, r in circles:
            # QGraphicsEllipseItem 用左上角+宽高
            ell = QGraphicsEllipseItem(float(x - r), float(y - r), float(2 * r), float(2 * r))
            ell.setBrush(QBrush(QColor(0, 120, 255, 80)))
            ell.setPen(QPen(QColor(0, 120, 255), 2))
            ell.setData(0, (int(x), int(y), int(r)))
            ell.setToolTip(f"圆心({x},{y}) r={r} — 点击选中")
            ell.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
            self._scene.addItem(ell)
            self._circle_items.append(ell)

    def clear_avatar_overlays(self):
        for item in self._circle_items:
            self._scene.removeItem(item)
        self._circle_items = []

    def get_boxes(self) -> list[TextBox]:
        return self._boxes

    def highlight_box(self, index: int):
        if 0 <= self._selected_index < len(self._box_items):
            self._apply_style(self._box_items[self._selected_index], selected=False)
        self._selected_index = index
        if 0 <= index < len(self._box_items):
            self._apply_style(self._box_items[index], selected=True)

    @staticmethod
    def _apply_style(item: QGraphicsPolygonItem, selected: bool):
        if selected:
            item.setBrush(QBrush(QColor(0, 255, 0, 100)))
            item.setPen(QPen(QColor(0, 200, 0), 3))
        else:
            item.setBrush(QBrush(QColor(255, 255, 0, 70)))
            item.setPen(QPen(QColor(255, 0, 0), 2))

    # ---------- 交互 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())

            if self.mode == "rect":
                # 开始橡皮筋矩形
                self._rubber_origin = self.mapToScene(event.pos())
                if self._rubber_item is not None:
                    self._scene.removeItem(self._rubber_item)
                self._rubber_item = QGraphicsRectItem(QRectF(self._rubber_origin, self._rubber_origin))
                self._rubber_item.setBrush(QBrush(QColor(0, 255, 0, 40)))
                self._rubber_item.setPen(QPen(QColor(0, 200, 0), 2))
                self._scene.addItem(self._rubber_item)
                return

            if self.mode == "circle":
                if isinstance(item, QGraphicsEllipseItem) and item in self._circle_items:
                    data = item.data(0)
                    if isinstance(data, tuple) and len(data) == 3:
                        self.circle_selected.emit(int(data[0]), int(data[1]), int(data[2]))
                        return
                # 点空白处：忽略
                return

            # normal 模式：bbox 选择
            if isinstance(item, QGraphicsPolygonItem):
                idx = int(item.data(0))
                self.highlight_box(idx)
                self.box_selected.emit(idx)
                return
            self.highlight_box(-1)
            self.box_selected.emit(-1)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mode == "rect" and self._rubber_origin is not None and self._rubber_item is not None:
            cur = self.mapToScene(event.pos())
            rect = QRectF(self._rubber_origin, cur).normalized()
            self._rubber_item.setRect(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mode == "rect" and event.button() == Qt.LeftButton:
            if self._rubber_item is not None and self._rubber_origin is not None:
                rect = self._rubber_item.rect().normalized()
                self._scene.removeItem(self._rubber_item)
                self._rubber_item = None
                self._rubber_origin = None
                w = int(round(rect.width()))
                h = int(round(rect.height()))
                x = int(round(rect.x()))
                y = int(round(rect.y()))
                # 恢复 normal 模式（单次框选）
                self.set_selection_mode("normal")
                if w >= 5 and h >= 5:  # 太小的框忽略
                    self.rect_selected.emit(x, y, w, h)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, QGraphicsPolygonItem):
            idx = int(item.data(0))
            self.box_double_clicked.emit(idx)
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)

    def fit_image(self):
        if self._pixmap_item is not None:
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
