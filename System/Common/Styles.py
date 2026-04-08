def make_button_style(
        bg_color:    str,
        hover_color: str,
        border:      str = None,
        rounding:    int = 16
    ) -> str:
    
    base = f"""
        QPushButton {{
            background-color: {bg_color};
            color: {Colors.FontColor};
            padding: 0px 15px;
            border-radius: {rounding}px;
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

class Colors:
    class EffectMenu:
        Standard    = "#2d2e31"
        Hover       = "#28292b"
        Press       = "#252628"

    class Waveform:
        MainColor = "#5AFFFFFF"

    class MainMenu:
        Button             = "#333333"
        ButtonHover        = "#444444"

        SmallButton        = "#3a3a3a"
        SmallButtonHover   = "#4a4a4a"

    NothingAccent          = "#d6141f"
    NothingAccentHover     = "#c20808"
    NothingAccentPressed   = "#ba0505"

    TitleFontColor         = "#ffffff"
    FontColor              = "#dddddd"
    SubtleFontColor        = "#9d9d9d"

    NormalButton           = "#2b2b2b"
    NormalButtonSecond     = "#404040"

    Background             = "#1f1f1f"
    SecondaryBackground    = "#2b2b2b"
    ThirdBackground        = "#232323"

    GlassBorder            = "#404040"

    class Floating:
        Background          = "#2b2b2b"
        Border              = "#404040"

        ElementBackground   = "#343434"

    class Waveline:
        BeatColor           = "#6A6A6A"
        TrackNameColor      = "#bbbbbb"

class Roundings:
    Button          = 16
    Slider          = 3
    SliderHandle    = 4

    RmbMenu         = 16
    RmbMenuItem     = 12

    Selection       = 10

class Metrics:
    ElementHeight   = 50
    GlassBorderThick = 1.5

    SliderHeight    = 6
    HandleSize      = 14

    CheckboxSize    = 16

    class Tracks:
        RulerHeight = 30
        RowHeight   = 50
        LabelWidth  = 50
        BoxHeight   = 40
        BoxSpacing  = 4

    class Waveform:
        Height      = 150

class Buttons:
    NothingStyledButton = make_button_style(
        Colors.NothingAccent,
        Colors.NothingAccentHover
    )

    NormalButton = make_button_style(
        Colors.NormalButton,
        Colors.NormalButtonSecond
    )

    NormalButtonWithBorder = make_button_style(
        Colors.NormalButton,
        Colors.NormalButtonSecond,
        f"{Metrics.GlassBorderThick}px solid {Colors.GlassBorder}"
    )

    NormalButtonWithBorderSlim = make_button_style(
        Colors.NormalButton,
        Colors.NormalButtonSecond,
        f"{Metrics.GlassBorderThick}px solid {Colors.GlassBorder}",
        12
    )

    class MainMenu:
        AccentButton = make_button_style(
            Colors.NothingAccent,
            Colors.NothingAccentHover,
            rounding = 20
        )

        NormalButton = make_button_style(
            Colors.MainMenu.Button,
            Colors.MainMenu.ButtonHover,
            rounding = 20
        )

        SmallButton = make_button_style(
            Colors.MainMenu.SmallButton,
            Colors.MainMenu.SmallButtonHover,
            rounding = 14
        )

    class Settings:
        CategoryInactiveButton = make_button_style(
            "transparent",
            Colors.NormalButtonSecond,
            rounding = 18
        )

        CategoryActiveButton = make_button_style(
            Colors.NothingAccent,
            Colors.NothingAccentHover,
            rounding = 18
        )

class Other:
    Transparent = "background-color: transparent;"

    StatusBar = f"""
        QLabel {{
            background-color: {Colors.SecondaryBackground};
            color: {Colors.FontColor};
            padding: 0px 10px;
            border-radius: {Roundings.Button}px;
            min-height: {Metrics.ElementHeight}px;
        }}
    """

    Font = f"""color: {Colors.TitleFontColor};"""
    Label = f"""color: {Colors.FontColor}; background-color: transparent; padding: 0;"""
    SecondFont = f"""color: {Colors.SubtleFontColor};"""

    Tooltip = f"""
        color: {Colors.FontColor};
        background-color: {Colors.SecondaryBackground};
        border-radius: {Roundings.Button};
        border: {Metrics.GlassBorderThick}px solid {Colors.GlassBorder}
    """

    GlassBorder = f"""
        border: {Metrics.GlassBorderThick}px solid {Colors.GlassBorder};
    """

class Controls:
    SegmentedButton = f"""
        QWidget {{ background-color: transparent; border-radius: 10px; }}

        QPushButton#segmentedButton {{
            color: {Colors.FontColor};
            background-color: {Colors.EffectMenu.Standard};
            border: none;
            padding: 0;
            border-radius: {Roundings.Button - 5}px;
            outline: none;
        }}

        QPushButton#segmentedButton:hover {{
            background-color: {Colors.EffectMenu.Hover};
        }}

        QPushButton#segmentedButton:checked {{
            background-color: {Colors.NothingAccent};
            color: #ffffff;
        }}
    """

    Selector = f"""
        QWidget {{
            background-color: transparent;
            border-radius: {Roundings.Button}px;
            border: 1.5px solid {Colors.GlassBorder};
        }}

        QPushButton#segmentedButton {{
            color: {Colors.FontColor};
            background-color: transparent;
            border: none;
            padding: 0;
            border-radius: {Roundings.Button - 2}px;
            outline: none;
        }}

        QPushButton#segmentedButton:hover {{
            background-color: {Colors.ThirdBackground};
        }}

        QPushButton#segmentedButton:checked {{
            background-color: {Colors.NothingAccent};
            color: #ffffff;
        }}

        QPushButton#segmentedButton:checked:hover {{
            background-color: {Colors.NothingAccentHover};
        }}
    """

    TextBoxNoBorder = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: {Roundings.Button}px;
    """

    FloatingTextBox = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: 15px;
        border: 1.5px solid {Colors.GlassBorder}
    """

    FloatingSearchTextBox = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: 20px;
        border: none
    """

    FloatingTextBoxRound = f"""
        background-color: transparent;
        color: #fff;
        padding: 8px 12px;
        border-radius: 16px;
        border: 1.5px solid {Colors.GlassBorder}
    """

    AudioSetupper = f"""
        QDialog {{
            background-color: {Colors.ThirdBackground};
        }}

        QLabel {{
            background: transparent;
            color: {Colors.FontColor};
        }}

        QLabel#settingsLabel {{
            color: #8A8A8A;
        }}

        QSpinBox {{
            background-color: transparent;
            border: none;
            padding: 5px;
            color: {Colors.FontColor};
        }}
        
        QComboBox {{
            background-color: {Colors.SecondaryBackground};
            color: {Colors.FontColor};
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
        QWidget {{background-color: {Colors.EffectMenu.Standard}; color: {Colors.FontColor}}}
        QLabel {{padding: 5px}}
        QCheckBox {{margin-left: 5px}}
    """

    SliderBackground = f"""
        QWidget {{
            background-color: {Colors.EffectMenu.Press};
            border-radius: {Roundings.Button}px;
        }}
        """

    Slider = f"""
        QSlider::groove:horizontal {{
            height: {Metrics.SliderHeight}px;
            background: {Colors.EffectMenu.Hover};
            border: 1px solid #555;
            border-radius: {Roundings.Slider}px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.NothingAccent};
            border: {Metrics.GlassBorderThick} solid {Colors.NothingAccent};
            border-radius: {Roundings.Slider}px;
        }}

        QSlider::add-page:horizontal {{
            background: {Colors.EffectMenu.Hover};
            border: {Metrics.GlassBorderThick} solid #555;
            border-radius: {Roundings.Slider}px;
        }}

        QSlider::handle:horizontal {{
            width: {Metrics.HandleSize};
            height: {Metrics.HandleSize};
            margin: -5px 0;
            background: {Colors.NothingAccent};
            border: none;
            border-radius: {Roundings.SliderHandle}px;
        }}

        QSlider::handle:horizontal:hover {{
            background: {Colors.NothingAccentHover};
        }}

        QSlider::handle:horizontal:pressed {{
            background: {Colors.NothingAccentPressed};
        }}
    """

    ValueControl = f"""
        DraggableValueControl {{
            background-color: {Colors.SecondaryBackground};
            border-radius: {Roundings.Button}px;
            border: {Metrics.GlassBorderThick}px solid {Colors.GlassBorder};
            min-height: {Metrics.ElementHeight}px;
        }}

        DraggableValueControl:hover {{
            background-color: {Colors.ThirdBackground};
        }}
    """

    CycleButton = f"""
        CycleButton {{
            background-color: {Colors.SecondaryBackground};
            border-radius: {Roundings.Button}px;
            border: {Metrics.GlassBorderThick}px solid {Colors.GlassBorder};
            min-height: {Metrics.ElementHeight}px;
        }}
        CycleButton:hover {{
            background-color: {Colors.ThirdBackground};
        }}
    """

    MiniWaveformPreview = f"""
        MiniWaveformPreview {{
            background-color: {Colors.SecondaryBackground};
            border-radius: {Roundings.Button}px;
            border: {Metrics.GlassBorderThick}px solid {Colors.GlassBorder};
            min-height: {Metrics.ElementHeight}px;
        }}
        MiniWaveformPreview:hover {{
            background-color: {Colors.ThirdBackground};
        }}
    """

    Checkbox = f"""
        QCheckBox {{
            spacing: 8px;
            color: {Colors.FontColor};
        }}

        QCheckBox::indicator {{
            width: {Metrics.CheckboxSize};
            height: {Metrics.CheckboxSize};
            border-radius: 5px;
            background-color: {Colors.EffectMenu.Hover};
            border: {Metrics.GlassBorderThick} solid #555;
        }}

        QCheckBox::indicator:hover {{
            border: {Metrics.GlassBorderThick} solid {Colors.NothingAccentPressed};
        }}

        QCheckBox::indicator:checked {{
            background-color: {Colors.NothingAccent};
            border: {Metrics.GlassBorderThick} solid {Colors.NothingAccent};
        }}
        """

    DialogBackground = """
        background-color: rgba(20, 20, 20, 220);
        border-radius: 16px;
    """


class Menus:
    RmbElement = f"""
        QMenu {{
            background-color: {Colors.EffectMenu.Standard};
            color: {Colors.FontColor};
            border: {Metrics.GlassBorderThick} solid {Colors.GlassBorder};
            border-radius: {Roundings.RmbMenu}px;
            padding: 4px;
        }}

        QMenu::item {{
            {Other.Transparent}
            padding: 5px 15px;
            margin: 2px;
            border-radius: {Roundings.RmbMenuItem}px;
        }}

        QMenu::item:selected {{
            background-color: {Colors.EffectMenu.Hover};
        }}

        QMenu::separator {{
            height: {Metrics.GlassBorderThick};
            background-color: {Colors.GlassBorder};
            margin: 4px 15px;
        }}
    """

    ContextMenu = f"""
        QMenu {{
            background-color: {Colors.EffectMenu.Standard};
            color: {Colors.FontColor};
            border: {Metrics.GlassBorderThick} solid {Colors.GlassBorder};
            border-radius: {Roundings.RmbMenu}px;
            padding: 4px;
        }}

        QMenu::item {{
            {Other.Transparent}
            padding: 5px 15px;
            margin: 2px;
            border-radius: {Roundings.RmbMenuItem}px;
        }}

        QMenu::item:selected {{
            background-color: {Colors.EffectMenu.Hover};
        }}

        QMenu::separator {{
            height: {Metrics.GlassBorderThick};
            background-color: {Colors.GlassBorder};
            margin: 4px 15px;
        }}
    """