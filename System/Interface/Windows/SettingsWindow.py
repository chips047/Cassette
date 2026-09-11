from PyQt6.QtCore import (
    Qt,
    QSettings
)

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QStackedWidget
)

from System.Common import (
    Utils,
    Styles,
    Constants
)

from System.Interface import Widgets

from System.Interface.Windows import FloatingWindowGPU

# Settings Window

class SettingsWindow(FloatingWindowGPU):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Settings",
            parent                     = parent,
            max_tilt_angle             = 10,
            enable_audioplayer_effects = False
        )

        self.settings         = QSettings("chips047", "Cassette")
        self.pages            = {}
        self.controls         = {}
        self.max_scroll_width = 0

        self.nav_widget       = self.setup_navigation()
        self.stacked_widget   = QStackedWidget()
        self.ok_button        = Widgets.NothingButton("Apply!")
        self.cancel_button    = Widgets.ButtonWithOutline("Cancel")

        self.stacked_widget.setStyleSheet("background: transparent;")
        self.title_label.setFont(Utils.NType(21))

        self.build_layout()
        self.connect_signals()

    # Setup

    def setup_navigation(self) -> QWidget:
        navigation_widget = QWidget()
        navigation_widget.setFixedHeight(40)
        navigation_widget.setStyleSheet(f"background: {Styles.Colors.ThirdBackground}; border-radius: 18px;")

        navigation_layout = QHBoxLayout(navigation_widget)
        navigation_layout.setContentsMargins(4, 4, 4, 4)
        navigation_layout.setSpacing(6)
        navigation_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.nav_layout = navigation_layout

        return navigation_widget

    def build_layout(self) -> None:
        button_row = QHBoxLayout()
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)

        self.content_layout.addWidget(self.nav_widget)
        self.content_layout.addWidget(self.stacked_widget)
        self.content_layout.addLayout(button_row)

    def connect_signals(self) -> None:
        self.ok_button.clicked.connect(self.apply_and_close)
        self.cancel_button.clicked.connect(self.on_cancel)

    # Pages

    def change_page(self, page_widget: QWidget) -> None:
        self.stacked_widget.setCurrentWidget(page_widget)

        for page_name, (button, widget) in self.pages.items():
            button.setActive(widget == page_widget)

    def initialize_settings(self, setting_components: dict) -> None:
        scroll_areas = []
        first_page   = None

        for page_name, components in setting_components.items():
            page_area = self.create_page(page_name, components, scroll_areas)

            if not first_page:
                first_page = page_area

        self.apply_uniform_width(scroll_areas)

        if first_page:
            self.change_page(first_page)

    def create_page(
            self,
            page_name:    str,
            components:   list,
            scroll_areas: list
        ) -> QWidget:

        page_area = Widgets.ElasticScrollArea(self)
        page_area.setFixedHeight(360)

        navigation_button = Widgets.NavButton(page_name)
        navigation_button.clicked.connect(lambda checked = False, target_page = page_area: self.change_page(target_page))
        self.nav_layout.addWidget(navigation_button)

        self.pages[page_name] = (navigation_button, page_area)

        for component_config in components:
            widget = self.create_input_widget(component_config)

            if widget:
                page_area.add_widget(widget)
                self.controls[component_config["key"]] = widget

        self.stacked_widget.addWidget(page_area)
        scroll_areas.append(page_area)

        return page_area

    def apply_uniform_width(self, scroll_areas: list) -> None:
        for scroll_area in scroll_areas:
            required_width = scroll_area.get_required_width()

            if required_width > self.max_scroll_width:
                self.max_scroll_width = required_width

        for scroll_area in scroll_areas:
            scroll_area.setFixedWidth(self.max_scroll_width)

    # Widgets

    def create_input_widget(self, config: dict) -> QWidget | None:
        value     = self.settings.value(config["key"])
        type_name = config["type"]

        if type_name == "checkbox":
            return self.create_checkbox_widget(value, config)

        if type_name == "slider":
            return self.create_slider_widget(value, config)

        if type_name == "selector":
            return self.create_selector_widget(value, config)

        if type_name == "delay_setup":
            return self.create_delay_setup_widget(value, config)

        return None

    def create_delay_setup_widget(
            self,
            value:  str,
            config: dict
        ) -> QWidget:

        delay_value = int(value or config["default"])

        return Widgets.DelaySetupper(
            config["description"],
            delay_value
        )

    def create_checkbox_widget(
            self,
            value:  str,
            config: dict
        ) -> QWidget:

        state = str(value).lower() == "true" if value is not None else config["default"]

        return Widgets.CheckboxWithLabel(
            config["title"],
            config["description"],
            state
        )

    def create_slider_widget(
            self,
            value:  str,
            config: dict
        ) -> QWidget:
        
        slider_value = int(value or config["default"])

        return Widgets.SliderWithLabel(
            config["title"],
            config["min"],
            config["max"],
            slider_value
        )

    def create_selector_widget(
            self,
            value:  str,
            config: dict
        ) -> QWidget:

        default_text  = config["default"] if value is None else None
        default_value = value

        return Widgets.SelectorWithLabel(
            config["title"],
            config["map"],
            default_text  = default_text,
            default_value = default_value
        )

    # Actions

    def apply_and_close(self) -> None:
        for key, widget in self.controls.items():
            self.save_widget_value(key, widget)

        self.settings.sync()
        Constants.load_settings()

        self.on_ok()

    def save_widget_value(
            self,
            key:    str,
            widget: QWidget
        ) -> None:

        if isinstance(widget, Widgets.CheckboxWithLabel):
            self.settings.setValue(key, widget.isChecked())
            return

        if isinstance(widget, Widgets.SliderWithLabel):
            self.settings.setValue(key, widget.value())
            return

        if isinstance(widget, Widgets.SelectorWithLabel):
            self.settings.setValue(key, widget.current_data())
            return

        if isinstance(widget, Widgets.DelaySetupper):
            self.settings.setValue(key, widget.current_value())