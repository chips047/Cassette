from __future__ import annotations

from PyQt6.QtGui import (
    QCursor,
    QShowEvent,
    QHideEvent,
    QMouseEvent,
    QCloseEvent
)

from PyQt6.QtCore import (
    Qt,
    QSize,
    QRect,
    QPoint,
    QRectF,
    QTimer,
    pyqtSignal
)

from PyQt6.QtWidgets import (
    QMenu,
    QWidget,
    QAction,
    QVBoxLayout,
    QApplication,
    QGraphicsItem,
    QGraphicsView
)

from loguru import logger

from System.Common import (
    Utils,
    Styles
)

from System.Interface import (
    Basic,
    Inputs,
    Widgets
)

from System.Services import GlyphEffects
from System.Interface.Animation import LoomEngine

class TriangleGuard:
    GUARD_MS: int = 220

    def __init__(self) -> None:
        self.active:          bool            = False
        self.triangle:        tuple    | None = None
        self.expire_callback: callable | None = None

        self.timer = Basic.Timer(
            self.GUARD_MS,
            self.expire,
            True
        )

    def arm(
        self,
        trigger_rect: QRect,
        submenu_rect: QRect,
        on_expire:    callable | None = None
    ) -> None:

        self.expire_callback = on_expire
        sg: QRect            = submenu_rect

        self.triangle = (
            (trigger_rect.right(), trigger_rect.center().y()),
            (sg.left(), sg.top()    - 8),
            (sg.left(), sg.bottom() + 8)
        )

        self.active = True
        self.timer.start()

    def disarm(self) -> None:
        self.active = False
        self.timer.stop()

    def expire(self) -> None:
        if self.active and self.expire_callback:
            self.expire_callback()
        self.active = False

    def is_safe(self, pos: QPoint) -> bool:
        if not self.active or not self.triangle:
            return False

        px, py                        = pos.x(), pos.y()
        (ax, ay), (bx, by), (cx, cy) = self.triangle

        abc: float = self.area(ax, ay, bx, by, cx, cy)
        pbc: float = self.area(px, py, bx, by, cx, cy)
        pac: float = self.area(ax, ay, px, py, cx, cy)
        pab: float = self.area(ax, ay, bx, by, px, py)

        return abs(abc - (pbc + pac + pab)) < 0.1

    def area(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float
    ) -> float:

        return abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2.0)


class AnimatedMenu(QMenu):
    def __init__(
        self,
        engine: LoomEngine.AnimationEngine | None = None,
        parent: QWidget                    | None = None
    ) -> None:

        super().__init__(parent)

        self.owns_engine: bool                        = engine is None
        self.engine:      LoomEngine.AnimationEngine = (
            engine if engine is not None else LoomEngine.AnimationEngine("PyQt6")
        )

        self.k_rect:    str = f"rect_{id(self)}"
        self.k_opacity: str = f"opacity_{id(self)}"

        self.morph_start_rect: QRect | None = None
        self.final_geometry:   QRect | None = None
        self.pending_close:    bool         = False

        self.close_timer = Basic.Timer(
            150,
            self.do_close,
            single_shot = True,
            parent = self
        )

        self.engine.add_properties(
            [
                (self.k_rect,    QRect(), LoomEngine.MixMode.NOMIX, self.setGeometry),
                (self.k_opacity, 1.0,     LoomEngine.MixMode.NOMIX, self.setWindowOpacity)
            ]
        )

        self.setWindowFlags(
            Qt.Tool                   |
            Qt.WindowType.FramelessWindowHint    |
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowStaysOnTopHint
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setStyleSheet(Styles.Menus.ContextMenu)
        self.setFont(Utils.NType(11))

    def clamp_geometry(
        self,
        pos:  QPoint,
        size: QSize
    ) -> QRect:

        geometry: QRect = QRect(pos, size)
        desktop:  QRect = QApplication.desktop().availableGeometry(pos)

        if geometry.right()  > desktop.right():  geometry.moveRight(desktop.right())
        if geometry.bottom() > desktop.bottom(): geometry.moveBottom(desktop.bottom())

        return geometry

    def showEvent(self, event: QShowEvent) -> None:
        self.pending_close = False
        self.close_timer.stop()

        self.engine.resume()
        super().showEvent(event)
        self.ensurePolished()

        target: QRect = self.final_geometry or QRect(QCursor.pos(), self.sizeHint())

        if self.morph_start_rect:
            self.setGeometry(self.morph_start_rect)
            self.setWindowOpacity(0.0)

            self.engine.set_property_base_value(self.k_rect,    QRect(self.morph_start_rect))
            self.engine.set_property_base_value(self.k_opacity, 0.0)

            self.engine.set_target_value(self.k_rect,    target, 320, LoomEngine.Easing.ease_out_cubic)
            self.engine.set_target_value(self.k_opacity, 1.0,    120, LoomEngine.Easing.smooth)

            self.morph_start_rect = None

        else:
            start: QRect = QRect(QCursor.pos(), QSize(1, 1))
            self.setGeometry(start)
            self.setWindowOpacity(0.0)

            self.engine.set_property_base_value(self.k_rect,    QRect(start))
            self.engine.set_property_base_value(self.k_opacity, 0.0)

            self.engine.set_target_value(self.k_rect,    target, 180, LoomEngine.Easing.ease_out_cubic)
            self.engine.set_target_value(self.k_opacity, 1.0,    160, LoomEngine.Easing.smooth)

        self.final_geometry = None

    def close_animated(self) -> None:
        print("CLOSE")
        current_geometry: QRect = self.geometry()

        self.engine.set_property_base_value(self.k_opacity, float(self.windowOpacity()))
        self.engine.set_property_base_value(self.k_rect,    current_geometry)

        self.engine.set_target_value(self.k_opacity, 0.0, 70, LoomEngine.Easing.smooth)
        self.engine.set_target_value(
            self.k_rect,
            QRect(
                int(current_geometry.x() + current_geometry.width()  * 0.25),
                int(current_geometry.y() + current_geometry.height() * 0.25),
                int(current_geometry.width()  * 0.75),
                int(current_geometry.height() * 0.75)
            ),
            180,
            LoomEngine.Easing.ease_out_cubic
        )

        self.pending_close = True
        self.close_timer.start()

    def do_close(self) -> None:
        if self.pending_close:
            self.close()

    def reopen_animated(self, final_geom: QRect) -> None:
        self.pending_close = False
        self.close_timer.stop()

        self.final_geometry   = None
        self.morph_start_rect = None

        self.engine.resume()

        self.engine.set_property_base_value(self.k_opacity, float(self.windowOpacity()))
        self.engine.set_property_base_value(self.k_rect,    self.geometry())

        self.engine.set_target_value(self.k_rect,    final_geom, 320, LoomEngine.Easing.ease_out_cubic)
        self.engine.set_target_value(self.k_opacity, 1.0,        120, LoomEngine.Easing.smooth)

    def execfrom_widget(
        self,
        widget:     QWidget | QGraphicsItem,
        target_pos: QPoint
    ) -> None:

        if isinstance(widget, QWidget):
            start_point: QPoint = widget.mapToGlobal(QPoint(0, 0))
            size:        QSize  = widget.size()

        elif isinstance(widget, QGraphicsItem):
            scene_rect:  QRectF        = widget.mapToScene(widget.boundingRect()).boundingRect()
            view:        QGraphicsView = widget.scene().views()[0]
            view_point:  QPoint        = view.mapFromScene(scene_rect.topLeft())
            start_point: QPoint        = view.viewport().mapToGlobal(view_point)
            size:        QSize         = scene_rect.size().toSize()

        self.morph_start_rect = QRect(start_point, size)

        self.engine.set_property_base_value(self.k_rect,    self.morph_start_rect)
        self.engine.set_property_base_value(self.k_opacity, 0.0)

        self.ensurePolished()

        self.final_geometry = self.clamp_geometry(target_pos, self.sizeHint())
        self.show()

    def execand_cleanup(self, pos: QPoint) -> None:
        self.ensurePolished()
        self.final_geometry = self.clamp_geometry(pos, self.sizeHint())
        self.show()

    def morph_to(
        self,
        new_entries:      list,
        final_pos_global: QPoint
    ) -> None:

        self.clear()
        self.entries = new_entries

        for label, data in self.entries:
            if label == "-":
                self.addSeparator()

            else:
                action: QAction = QAction(label, self)
                action.setData({"type": "branch" if isinstance(data, list) else "leaf", "data": data})

                if not data:
                    action.setEnabled(False)

                self.addAction(action)

        final_geom: QRect = self.clamp_geometry(final_pos_global, self.sizeHint())

        self.engine.set_target_value(self.k_opacity, 1.0,        200, LoomEngine.Easing.smooth)
        self.engine.set_target_value(self.k_rect,    final_geom, 280, LoomEngine.Easing.ease_out_cubic)
        self.morph_start_rect = None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_timer.stop()
        self.pending_close = False

        if self.owns_engine:
            self.engine.clear()

        super().closeEvent(event)


class CustomWidgetPopup(AnimatedMenu):
    def __init__(
        self,
        widget: QWidget,
        engine: LoomEngine.AnimationEngine,
        parent: QWidget | None = None
    ) -> None:

        super().__init__(engine, parent)

        self.widget: QWidget = widget

        widget.setParent(self)

        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

    def sizeHint(self) -> QSize:
        return self.widget.sizeHint()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.engine.set_property_base_value(self.k_rect,    QRect())
        self.engine.set_property_base_value(self.k_opacity, 1.0)
        self.close_timer.stop()
        self.pending_close = False

        super().closeEvent(event)

    def close_all_animated(self) -> None:
        self.close_animated()


class ContextMenu(AnimatedMenu):
    def __init__(
        self,
        entries: list,
        parent:  QWidget                    | None = None,
        is_sub:  bool                              = False,
        root:    ContextMenu                | None = None,
        engine:  LoomEngine.AnimationEngine | None = None
    ) -> None:

        super().__init__(engine, parent)

        self.active_submenu: ContextMenu | CustomWidgetPopup | None = None
        self.hovered_action: QAction                         | None = None

        self.root:         ContextMenu                          = root or self
        self.is_sub:       bool                                 = is_sub
        self.entries:      list                                 = entries
        self.widget_cache: dict[QAction, CustomWidgetPopup]     = {}

        self.hover_timer = Basic.Timer(
            70,
            self.open_hovered_submenu,
            single_shot = True,
            parent = self
        )

        self.guard = TriangleGuard()

        self.aboutToHide.connect(self.on_about_to_hide)

        self.populate()

    def populate(self) -> None:
        self.clear()

        for label, data in self.entries:
            if label == "-":
                self.addSeparator()
                continue

            action: QAction = QAction(label, self)

            if isinstance(data, list):
                action.setData({"type": "branch", "data": data})

            elif isinstance(data, (QWidget, type)):
                action.setData({"type": "custom_widget", "data": data})

            else:
                action.setData({"type": "leaf", "data": data})

            if not data:
                action.setEnabled(False)

            self.addAction(action)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)

        gpoint: QPoint = self.mapToGlobal(event.pos())

        if (
            self.active_submenu             and
            self.active_submenu.isVisible() and
            self.active_submenu.geometry().contains(gpoint)
        ):
            return

        if self.guard.is_safe(gpoint):
            return

        self.guard.disarm()

        action: QAction | None = self.actionAt(event.pos())

        if action != self.hovered_action:
            self.hovered_action = action
            self.hover_timer.start()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        action: QAction | None = self.actionAt(event.pos())

        if not action or not action.isEnabled():
            return super().mouseReleaseEvent(event)

        data: dict | None = action.data()

        if not data:
            return super().mouseReleaseEvent(event)

        item_type: str = data.get("type", "")

        if item_type == "leaf":
            callback: callable | None = data.get("data")

            if callback:
                self.root.close_all_animated()

                QTimer.singleShot(10, callback)

            return

        elif item_type in ("branch", "custom_widget"):
            return

        super().mouseReleaseEvent(event)

    def open_hovered_submenu(self) -> None:
        data_map:  dict | None = self.hovered_action.data() if self.hovered_action else None
        item_type: str  | None = data_map.get("type") if data_map else None

        if item_type not in ("branch", "custom_widget"):
            if self.active_submenu:
                self.active_submenu.close_animated()
                self.active_submenu = None
            return

        content: object = data_map["data"]

        prev_geom: QRect | None = (
            self.active_submenu.geometry()
            if self.active_submenu and self.active_submenu.isVisible()
            else None
        )

        if self.active_submenu:
            self.active_submenu.close_animated()
            self.active_submenu = None

        rect: QRect  = self.actionGeometry(self.hovered_action)
        pos:  QPoint = self.mapToGlobal(QPoint(rect.right() - 5, rect.top()))

        if item_type == "branch":
            submenu:    ContextMenu = ContextMenu(content, self, True, self.root, self.root.engine)
            final_geom: QRect       = self.clamp_geometry(pos, submenu.sizeHint())

            submenu.final_geometry = final_geom

            if prev_geom:
                submenu.morph_start_rect = prev_geom
                submenu.engine.set_property_base_value(submenu.k_rect,    prev_geom)
                submenu.engine.set_property_base_value(submenu.k_opacity, 0.0)

            self.guard.arm(rect, final_geom)
            self.active_submenu = submenu
            submenu.show()

        elif item_type == "custom_widget":
            if self.hovered_action not in self.widget_cache:
                widget: QWidget = content() if isinstance(content, type) else content

                popup: CustomWidgetPopup = CustomWidgetPopup(widget, self.root.engine, self)
                popup.ensurePolished()
                popup.adjustSize()

                self.widget_cache[self.hovered_action] = popup

            popup:      CustomWidgetPopup = self.widget_cache[self.hovered_action]
            final_geom: QRect             = self.clamp_geometry(pos, popup.sizeHint())

            self.guard.arm(rect, final_geom)
            self.active_submenu = popup

            if popup.isVisible():
                popup.reopen_animated(final_geom)

            else:
                popup.final_geometry = final_geom

                if prev_geom:
                    popup.morph_start_rect = prev_geom
                    popup.engine.set_property_base_value(popup.k_rect,    prev_geom)
                    popup.engine.set_property_base_value(popup.k_opacity, 0.0)

                popup.show()

    def on_about_to_hide(self) -> None:
        if self.active_submenu:
            self.active_submenu.close()
            self.active_submenu = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.active_submenu:
            self.active_submenu.close()
            self.active_submenu = None

        for popup in self.widget_cache.values():
            popup.close()

        self.widget_cache.clear()

        super().closeEvent(event)

    def close_all_animated(self) -> None:
        if self.active_submenu:
            self.active_submenu.close_all_animated()
            self.active_submenu = None

        for popup in self.widget_cache.values():
            popup.close()

        self.widget_cache.clear()

        self.close_animated()


class EffectPreviewWidget(QWidget):
    apply_requested: pyqtSignal = pyqtSignal(str, dict)

    def __init__(
        self,
        effect_name: str,
        config:      dict,
        glyph:       dict,
        parent:      QWidget | None = None
    ) -> None:

        super().__init__(parent)

        self.effect_name: str  = effect_name
        self.config:      dict = config
        self.glyph:       dict = glyph
        self.controls:    dict = {}

        self.effect_info: dict = GlyphEffects.EffectsConfig.get(self.effect_name, {})

        self.setup_ui()
        self.populate_controls()
        self.on_control_changed()

        logger.debug(f"Created Effect Previewer for {effect_name}")

    def setup_ui(self) -> None:
        self.setFixedWidth(400)
        self.setStyleSheet(Styles.Controls.EffectSetupper)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(12)

        self.live_preview_bar: Widgets.ScheduledSegmentedBar = Widgets.ScheduledSegmentedBar(30, loop=True)
        self.main_layout.addWidget(self.live_preview_bar)

        self.apply_button: Basic.NothingButton = Basic.NothingButton("Apply")
        self.apply_button.clicked.connect(self.on_apply)

    def populate_controls(self) -> None:
        types_map: dict = {
            "checkbox": (Inputs.Checkbox,          "stateChanged"),
            "slider":   (Inputs.SliderWithLabel,   "valueChanged"),
            "selector": (Inputs.SelectorWithLabel, "selectionChanged")
        }

        logger.debug(f"Populating controls for Effect {self.effect_name}")

        for item in self.effect_info.get("settings", []):
            logger.debug(f"Adding control: {item['title']}")

            itype:                str = item.get("type")
            widget_class, signal_name = types_map[itype]

            if itype == "slider":
                widget:        QWidget = widget_class(item["title"], item["min"], item["max"], item["default"])
                change_signal          = widget.slider.valueChanged

            elif itype == "selector":
                widget:        QWidget = widget_class(item["title"], item["map"], item["default"])
                change_signal          = getattr(widget, signal_name)

            elif itype == "checkbox":
                widget:        QWidget = widget_class(item["title"], item["default"])
                change_signal          = getattr(widget, signal_name)

            change_signal.connect(self.on_control_changed)

            self.main_layout.addWidget(widget)
            self.controls[item["key"]] = widget

        self.main_layout.addWidget(self.apply_button)

    def get_settings(self) -> dict:
        settings: dict = {}

        for key, widget in self.controls.items():
            if isinstance(widget, Inputs.Checkbox):
                settings[key] = widget.isChecked()

            elif isinstance(widget, Inputs.SliderWithLabel):
                settings[key] = widget.value()

            elif isinstance(widget, Inputs.SelectorWithLabel):
                settings[key] = widget.currentData()

        return settings

    def _generate_effect_track(self) -> None:
        logger.debug("Setting new effect track...")

        settings: dict = self.get_settings()
        glyph:    dict = GlyphEffects.generate_glyph_dict(
            duration   = max(self.glyph["duration"], 3000),
            brightness = self.glyph["brightness"]
        )

        prepared_glyph: list = [GlyphEffects.apply_visual_effect(glyph, self.effect_name, settings)]

        if "effect" in prepared_glyph[0]:
            prepared_glyph = GlyphEffects.effect_to_glyph(
                GlyphEffects.apply_visual_effect(glyph, self.effect_name, settings),
                120
            )

        self.live_preview_bar.set_schedule(prepared_glyph)

    def on_control_changed(self, *args: object) -> None:
        self.apply_button.setText("Apply")
        self.apply_button.setDisabled(False)
        self._generate_effect_track()

    def on_apply(self) -> None:
        self.apply_button.setText("Applied")
        self.apply_button.setDisabled(True)
        self.apply_requested.emit(self.effect_name, self.get_settings())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        logger.debug(f"Starting Effect Visualizer on {self.effect_name}")
        self.live_preview_bar.play()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        logger.debug(f"Stopping Effect Visualizer on {self.effect_name}")
        self.live_preview_bar.stop()