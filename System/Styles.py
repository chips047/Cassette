def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

class Colors:
    effect_menu = "#2d2e31"
    effect_menu_second = "#28292b"
    effect_menu_third = "#252628"
    
    nothing_accent = "#d6141f"
    nothing_accent_second = "#d20202"
    nothing_accent_third = "#ba0505"
    
    black = "#000000"
    font_color = "#dddddd"
    second_font_color = "#9d9d9d"
    
    green_button = "#4CAF50"
    green_button_second = "#45a049"
    
    normal_button = "#2b2b2b"
    normal_button_second = "#262626"
    
    background = "#1f1f1f"
    secondary_background = "#2b2b2b"
    third_background = "#232323"
    
    element_background = "#ffffff"
    
    glass_border = "#404040"
    
    class Waveline:
        beat_color = "#888888"
        track_name_color = "#bbbbbb"

class Roundings:
    button = 16
    slider = 3
    slider_handle = 4
    
    rmb_menu = 18
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
    rounding = Roundings.button
    height = 50
    
    green_button = f"""
        QPushButton {{ background-color: {Colors.green_button}; color: {Colors.font_color}; padding: 0px 15px; border-radius: {rounding}px; min-height: {height}px;}}
        QPushButton:hover {{ background-color: {Colors.green_button_second}; }}
    """
    
    nothing_styled_button = f"""
        QPushButton {{background-color: {Colors.nothing_accent}; color: {Colors.font_color}; padding: 0px 15px; border-radius: {rounding}px; height: {height}px;}}
        QPushButton:hover {{background-color: {Colors.nothing_accent_second}}}
        QPushButton:disabled {{background-color: #777777; color: #dddddd}}
    """
    
    normal_button = f"""
        QPushButton {{background-color: {Colors.normal_button}; color: {Colors.font_color}; padding: 0px 15px; border-radius: {rounding}px; height: {height}px;}}
        QPushButton:hover {{background-color: {Colors.normal_button_second}}}
    """

    normal_button_with_border = f"""
        QPushButton {{background-color: {Colors.normal_button}; color: {Colors.font_color}; padding: 0px 15px; border-radius: {rounding}px; height: {height}px; border: {Metrics.glass_border_thick}px solid {Colors.glass_border};}}
        QPushButton:hover {{background-color: {Colors.normal_button_second}}}
    """

class Other:
    transparent = "background-color: transparent;"
    black = "background-color: black;"
    
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
    second_font = f"""color: {Colors.second_font_color};"""
    
    Tooltip = f"""
    color: {Colors.font_color};
    background-color: {Colors.effect_menu_second};
    border-radius: {Roundings.button};
    border: {Metrics.glass_border_thick}px solid {Colors.glass_border}
    """

    glass_border = f"""
    border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
    """

class Controls:
    ComboBox = f"""
        QComboBox {{
            background-color: {Colors.secondary_background};
            color: #eeeeee;
            border: 1px solid {Colors.glass_border};
            border-radius: {Roundings.button}px;
            padding-left: 10px;
        }}
        QComboBox:hover {{
            background-color: {Colors.secondary_background};
            border: 1px solid {Colors.nothing_accent};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left-width: 1px;
            border-left-color: {Colors.glass_border};
            border-left-style: solid;
            border-top-right-radius: {Roundings.button}px;
            border-bottom-right-radius: {Roundings.button}px;
        }}
        QComboBox::down-arrow {{
            image: url(path/to/your/arrow-down-icon.png);
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: #2c2f33;
            color: #dddddd;
            border: 1px solid {Colors.nothing_accent};
            border-radius: 5px;
            selection-background-color: {Colors.nothing_accent};
            selection-color: white;
            padding: 4px;
            outline: 0px; /* Убирает рамку фокуса в Windows */
        }}
    """
    
    Selector = f"""
    
    /* сам корневой виджет */
        QWidget#selectorRoot {{
            background-color: {Colors.effect_menu_third};
            border-radius: {Roundings.button}px;
        }}

        /* внутренний фон — тот же цвет и радиус */
        #selectorWidget {{
            background-color: {Colors.effect_menu_third};
            border-radius: {Roundings.button}px;
        }}
        
        #backgroundContainer {{
            background-color: {Colors.effect_menu_third};
            border-radius: {Roundings.button}px;
        }}

        /* обычное состояние */
        QPushButton#segmentedButton {{
            color: {Colors.font_color};
            background-color: {Colors.effect_menu};
            border: none;
            padding: 0;                 /* чуть больше воздуха */
            border-radius: {Roundings.button - 5}px;
        }}

        /* навели курсор — подсветка слегка темнее фона */
        QPushButton#segmentedButton:hover {{
            background-color: {Colors.effect_menu_second};
        }}

        /* выбранный сегмент — красный акцент */
        QPushButton#segmentedButton:checked {{
            background-color: {Colors.nothing_accent};
            color: #ffffff;                 /* белый текст читается лучше */
        }}
        QPushButton#segmentedButton:checked:hover {{
            background-color: {Colors.nothing_accent_second};
        }}
    """
    
    Selector2 = f"""
        /* Style for the QWidget that contains the buttons */
        /* This will apply to the 'selector_container' in your Python code */
        QWidget {{
            background-color: {Colors.secondary_background}; /* No background for the container itself */
            border-radius: {Roundings.button}px;
        }}

        /* Normal state of the segmented button */
        QPushButton#segmentedButton {{
            color: {Colors.font_color};
            background-color: transparent;
            border: none;
            padding: 0;
            border-radius: {Roundings.button}px; /* Slightly smaller radius for individual buttons */
        }}

        /* Hover state for the segmented button */
        QPushButton#segmentedButton:hover {{
            background-color: {Colors.third_background};
        }}

        /* Checked state for the segmented button */
        QPushButton#segmentedButton:checked {{
            background-color: {Colors.nothing_accent};
            color: #ffffff;
        }}

        /* Hover state for the checked segmented button */
        QPushButton#segmentedButton:checked:hover {{
            background-color: {Colors.nothing_accent_second};
        }}
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
        QWidget {{background-color: {Colors.effect_menu}; color: {Colors.font_color}}}
        QLabel {{padding: 5px}}
        QCheckBox {{margin-left: 5px}}
    """
    
    SliderBackground = f"""
        QWidget {{
            background-color: {Colors.effect_menu_third};
            border-radius: {Roundings.button}px;
        }}
        """
    
    Slider = f"""
        QSlider::groove:horizontal {{
            height: {Metrics.slider_height}px;
            background: {Colors.effect_menu_second};
            border: 1px solid #555;
            border-radius: {Roundings.slider}px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.nothing_accent};
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent};
            border-radius: {Roundings.slider}px;
        }}

        QSlider::add-page:horizontal {{
            background: {Colors.effect_menu_second};
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
            background: {Colors.nothing_accent_second};
        }}

        QSlider::handle:horizontal:pressed {{
            background: {Colors.nothing_accent_third};
        }}
    """
    
    ValueControl = f"""
        DraggableValueControl {{ 
            background-color: {Colors.secondary_background}; 
            border-radius: {Roundings.button}px;
            border: {Metrics.glass_border_thick}px solid {Colors.glass_border};
            min-height: {Metrics.element_height}px;
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
    
    Checkbox = f"""
        QCheckBox {{
            spacing: 8px;
            color: {Colors.font_color};
        }}

        QCheckBox::indicator {{
            width: {Metrics.checkbox_size};
            height: {Metrics.checkbox_size};
            border-radius: 5px;
            background-color: {Colors.effect_menu_second};
            border: {Metrics.glass_border_thick} solid #555;
        }}

        QCheckBox::indicator:hover {{
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent};
        }}

        QCheckBox::indicator:checked {{
            background-color: {Colors.effect_menu_second};
            border: {Metrics.glass_border_thick} solid {Colors.nothing_accent};
            image: url(System/Icons/Dot.png);
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
        background-color: {Colors.effect_menu};
        color: {Colors.font_color};
        border: {Metrics.glass_border_thick} solid {Colors.glass_border};
        border-radius: {Roundings.rmb_menu}px;
        padding: 4px;
    }}

    QMenu::item {{
        {Other.transparent}
        padding: 5px 20px;
        margin: 2px;
        border-radius: {Roundings.rmb_menu_item}px;
    }}

    QMenu::item:selected {{
        background-color: {Colors.effect_menu_second};
    }}

    QMenu::separator {{
        height: {Metrics.glass_border_thick};
        background-color: {Colors.glass_border};
        margin: 4px 10px;
    }}
    """

    audio_setup = f"""
        QDialog {{
            background-color: #1e1e1e;
        }}
        QLabel {{
            color: #dddddd;
        }}
        QLabel#settingsLabel {{
            color: #8A8A8A;
        }}
        QSpinBox {{
            background-color: transparent;
            color: #dddddd;
            border: none;
            padding: 5px;
        }}
        QComboBox {{
            background-color: #2b2b2b;
            color: #dddddd;
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