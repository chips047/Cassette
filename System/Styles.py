def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

class Colors:
    class EffectMenu:
        standard = "#2d2e31"
        hover = "#28292b"
        press = "#252628"
    
    nothing_accent = "#d6141f"
    nothing_accent_hover = "#c20808"
    nothing_accent_pressed = "#ba0505"
    
    font_color = "#dddddd"
    subtle_font_color = "#9d9d9d"
    
    normal_button = "#2b2b2b"
    normal_button_second = "#404040"
    
    background = "#1f1f1f"
    secondary_background = "#2b2b2b"
    third_background = "#232323"
    
    glass_border = "#404040"

    class Floating:
        background = "#2b2b2b"
        border = "#404040"

        element_background = "#343434"

    class Waveline:
        beat_color = "#6A6A6A"
        track_name_color = "#bbbbbb"

class Roundings:
    button = 16
    slider = 3
    slider_handle = 4
    
    rmb_menu = 16
    rmb_menu_item = 12
    
    selection = 10

class Metrics:
    element_height = 50
    glass_border_thick = 1.5
    
    slider_height = 6
    handle_size = 14
    
    checkbox_size = 16
    
    class Tracks:
        ruler_height = 30
        row_height = 50
        label_width = 50
        box_height = 40
        box_spacing = 4
    
    class Waveform:
        height = 150

class Buttons:
    def make_button_style(
        bg_color: str,
        hover_color: str,
        height: int = 50,
        border: str = None,
        rounding = Roundings.button
    ) -> str:

        base = f"""
            QPushButton {{
                background-color: {bg_color};
                color: {Colors.font_color};
                padding: 0px 15px;
                border-radius: {rounding}px;
                height: {height}px;
                outline: none;
                {f"border: {border};" if border else ""}
            }}

            QPushButton:hover {{
                background-color: {hover_color};
            }}

            QPushButton:disabled {{
                background-color: #777777;
                color: #dddddd;
            }}
        """

        return base.strip()

    nothing_styled_button = make_button_style(
        Colors.nothing_accent,
        Colors.nothing_accent_hover
    )

    normal_button = make_button_style(
        Colors.normal_button,
        Colors.normal_button_second
    )

    normal_button_with_border = make_button_style(
        Colors.normal_button,
        Colors.normal_button_second,
        50,
        f"{Metrics.glass_border_thick}px solid {Colors.glass_border}"
    )

    normal_button_with_border_slim = make_button_style(
        Colors.normal_button,
        Colors.normal_button_second,
        35,
        f"{Metrics.glass_border_thick}px solid {Colors.glass_border}",
        12
    )

class Other:
    transparent = "background-color: transparent;"
    
    status_bar = f"""
        QLabel {{
            background-color: {Colors.secondary_background};
            color: {Colors.font_color};
            padding: 0px 10px;
            border-radius: {Roundings.button}px;
            min-height: {Metrics.element_height}px;
        }}
    """
    
    font = f"""color: {Colors.font_color};"""
    label = f"""color: {Colors.font_color}; background-color: transparent; padding: 0;"""
    second_font = f"""color: {Colors.subtle_font_color};"""
    
    Tooltip = f"""
        color: {Colors.font_color};
        background-color: {Colors.secondary_background};
        border-radius: {Roundings.button};
        border: {Metrics.glass_border_thick}px solid {Colors.glass_border}
    """

    glass_border = f"""
        border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
    """

class Controls:
    SegmentedButton = f"""
        QWidget {{ background-color: transparent; border-radius: 10px; }}

        QPushButton#segmentedButton {{
            color: {Colors.font_color};
            background-color: {Colors.EffectMenu.standard};
            border: none;
            padding: 0;
            border-radius: {Roundings.button - 5}px;
            outline: none;
        }}

        QPushButton#segmentedButton:hover {{
            background-color: {Colors.EffectMenu.hover};
        }}

        QPushButton#segmentedButton:checked {{
            background-color: {Colors.nothing_accent};
            color: #ffffff;
        }}
    """
    
    Selector2 = f"""
        QWidget {{
            background-color: transparent;
            border-radius: {Roundings.button}px;
            border: 1.5px solid {Colors.glass_border};
        }}

        QPushButton#segmentedButton {{
            color: {Colors.font_color};
            background-color: transparent;
            border: none;
            padding: 0;
            border-radius: {Roundings.button - 2}px;
            outline: none;
        }}

        QPushButton#segmentedButton:hover {{
            background-color: {Colors.third_background};
        }}

        QPushButton#segmentedButton:checked {{
            background-color: {Colors.nothing_accent};
            color: #ffffff;
        }}

        QPushButton#segmentedButton:checked:hover {{
            background-color: {Colors.nothing_accent_hover};
        }}
    """
    
    TextBoxNoBorder = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: {Roundings.button}px;
    """

    FloatingTextBox = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: 10px;
        border: 1.5px solid {Colors.glass_border}
    """

    FloatingTextBoxRound = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: 16px;
        border: 1.5px solid {Colors.glass_border}
    """

    AudioSetupper = f"""
        QDialog {{
            background-color: {Colors.third_background};
        }}
        QLabel {{
            background: transparent;
            color: {Colors.font_color};
        }}
        QLabel#settingsLabel {{
            color: #8A8A8A;
        }}
        QSpinBox {{
            background-color: transparent;
            border: none;
            padding: 5px;
            color: {Colors.font_color};
        }}
        QComboBox {{
            background-color: {Colors.secondary_background};
            color: {Colors.font_color};
            border: none;
            padding: 5px;
        }}

        QComboBox::down-arrow {{ image: none; }}
        QComboBox::drop-down {{ width: 0px; border: none; }}

        QComboBox QAbstractItemView::item:focus {{
            outline: none;
        }}

        QComboBox QAbstractItemView {{
            background: #2b2b2b;
            border: none;
            margin: 2px;
            color: #dddddd;
            selection-background-color: #1f1f1f;
            selection-color: #ffffff;
            outline: none;
        }}

        QComboBox::item:selected {{
            background: #1f1f1f;
            color: #ffffff;
        }}

        QPushButton#play_button {{
            background-color: transparent;
            border: none;
        }}
    """
    
    EffectSetupper = f"""
        QWidget {{background-color: {Colors.EffectMenu.standard}; color: {Colors.font_color}}}
        QLabel {{padding: 5px}}
        QCheckBox {{margin-left: 5px}}
    """
    
    SliderBackground = f"""
        QWidget {{
            background-color: {Colors.EffectMenu.press};
            border-radius: {Roundings.button}px;
        }}
        """
    
    Slider = f"""
        QSlider::groove:horizontal {{
            height: {Metrics.slider_height}px;
            background: {Colors.EffectMenu.hover};
            border: 1px solid #555;
            border-radius: {Roundings.slider}px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.nothing_accent};
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent};
            border-radius: {Roundings.slider}px;
        }}

        QSlider::add-page:horizontal {{
            background: {Colors.EffectMenu.hover};
            border: {Metrics.glass_border_thick} solid #555;
            border-radius: {Roundings.slider}px;
        }}

        QSlider::handle:horizontal {{
            width: {Metrics.handle_size};
            height: {Metrics.handle_size};
            margin: -5px 0;
            background: {Colors.nothing_accent};
            border: none;
            border-radius: {Roundings.slider_handle}px;
        }}

        QSlider::handle:horizontal:hover {{
            background: {Colors.nothing_accent_hover};
        }}

        QSlider::handle:horizontal:pressed {{
            background: {Colors.nothing_accent_pressed};
        }}
    """
    
    ValueControl = f"""
        DraggableValueControl {{ 
            background-color: {Colors.secondary_background}; 
            border-radius: {Roundings.button}px;
            border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
            min-height: {Metrics.element_height}px;
        }}

        DraggableValueControl:hover {{
            background-color: {Colors.third_background}; 
        }}
    """
    
    CycleButton = f"""
        CycleButton {{
            background-color: {Colors.secondary_background};
            border-radius: {Roundings.button}px;
            border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
            min-height: {Metrics.element_height}px;
        }}
        CycleButton:hover {{
            background-color: {Colors.third_background}; 
        }}
    """
    
    MiniWaveformPreview = f"""
        MiniWaveformPreview {{
            background-color: {Colors.secondary_background};
            border-radius: {Roundings.button}px;
            border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
            min-height: {Metrics.element_height}px;
        }}
        MiniWaveformPreview:hover {{
            background-color: {Colors.third_background}; 
        }}
    """

    Checkbox = f"""
        QCheckBox {{
            spacing: 8px;
            color: {Colors.font_color};
        }}

        QCheckBox::indicator {{
            width: {Metrics.checkbox_size};
            height: {Metrics.checkbox_size};
            border-radius: 5px;
            background-color: {Colors.EffectMenu.hover};
            border: {Metrics.glass_border_thick} solid #555;
        }}

        QCheckBox::indicator:hover {{
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent_pressed};
        }}

        QCheckBox::indicator:checked {{
            background-color: {Colors.nothing_accent};
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent};
        }}
        """
    
    DialogBackground = """
        background-color: rgba(20, 20, 20, 220);
        border-radius: 16px;
    """
    
    InputField = """
        background-color: #222;
        color: #fff;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid #444;
    """

class Menus:
    RMB_element = f"""
        QMenu {{
            background-color: {Colors.EffectMenu.standard};
            color: {Colors.font_color};
            border: {Metrics.glass_border_thick} solid {Colors.glass_border};
            border-radius: {Roundings.rmb_menu}px;
            padding: 4px;
        }}

        QMenu::item {{
            {Other.transparent}
            padding: 5px 15px;
            margin: 2px;
            border-radius: {Roundings.rmb_menu_item}px;
        }}

        QMenu::item:selected {{
            background-color: {Colors.EffectMenu.hover};
        }}

        QMenu::separator {{
            height: {Metrics.glass_border_thick};
            background-color: {Colors.glass_border};
            margin: 4px 15px;
        }}
    """