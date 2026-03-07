"""
PnL Card Generator Service
Generates trading PnL flex cards with custom styling
"""
import io
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from utils.logger import get_logger

logger = get_logger()

# === TEMPLATE & FONT PATHS ===
TEMPLATE_DIR = Path("assets/templates")
FONT_DIR = Path("assets/fonts")

TEMPLATES = {
    "BUY": [
        TEMPLATE_DIR / "buy_template_1.png",
        TEMPLATE_DIR / "buy_template_2.png"
    ],
    "SELL": [
        TEMPLATE_DIR / "sell_template_1.png",
        TEMPLATE_DIR / "sell_template_2.png"
    ]
}

FONTS = {
    "pnl": FONT_DIR / "RAPJACK_.TTF",        # Large purple/red %
    "text": FONT_DIR / "SpaceMono-Regular.ttf"  # Headers / prices
}

# === CONFIGS PER TEMPLATE (positions + color + anchors) ===
TEMPLATE_CONFIGS = {
    "buy_template_1.png": {
        "positions": {
            "symbol": (545, 174),
            "leverage": (1120, 177),
            "pnl_percentage": (800, 350),
            "entry_price": (520, 747),
            "mark_price": (510, 819),
            "username": (900, 610)
        },
        "anchors": {
            "symbol": "rt",           # ← Right-anchor: grows LEFT
            "leverage": "lt",
            "pnl_percentage": "rt",   # ← Right-anchor: grows LEFT
            "entry_price": "lt",
            "mark_price": "lt",
            "username": "rt"
        },
        "pnl_color": (220, 20, 60, 255)  # 🔴 red
    },
    "buy_template_2.png": {
        "positions": {
            "symbol": (650, 203),
            "leverage": (1220, 207),
            "pnl_percentage": (850, 375),
            "entry_price": (630, 777),
            "mark_price": (620, 849),
            "username": (1000, 635)
        },
        "anchors": {
            "symbol": "rt",          
            "leverage": "lt",
            "pnl_percentage": "rt",   
            "entry_price": "lt",
            "mark_price": "lt",
            "username": "rt"
        },
        "pnl_color": (180, 0, 255, 255)  # 🟣 purple
    },
    "sell_template_1.png": {
        "positions": {
            "symbol": (545, 174),
            "leverage": (1120, 177),
            "pnl_percentage": (800, 350),
            "entry_price": (520, 747),
            "mark_price": (510, 819),
            "username": (900, 610)
        },
        "anchors": {
            "symbol": "rt",           # ← Right-anchor: grows LEFT
            "leverage": "lt",
            "pnl_percentage": "rt",   # ← Right-anchor: grows LEFT
            "entry_price": "lt",
            "mark_price": "lt",
            "username": "rt"
        },
        "pnl_color": (220, 20, 60, 255)
    },
    "sell_template_2.png": {
        "positions": {
            "symbol": (650, 203),
            "leverage": (1220, 207),
            "pnl_percentage": (850, 375),
            "entry_price": (630, 777),
            "mark_price": (620, 849),
            "username": (1000, 635)
        },
        "anchors": {
            "symbol": "rt",           # ← Right-anchor: grows LEFT
            "leverage": "lt",
            "pnl_percentage": "rt",   # ← Right-anchor: grows LEFT
            "entry_price": "lt",
            "mark_price": "lt",
            "username": "rt"
        },
        "pnl_color": (180, 0, 255, 255)
    }
}

# === FONT SIZES ===
FONT_SIZES = {
    "pnl": 300,
    "header": 73,
    "price": 50,
    "username": 48  
}

# === COLORS ===
COLORS = {
    "soft_grey": (185, 185, 188, 255),  # 🩶 exact soft grey tone
    "white": (255, 255, 255, 255),
    "username_glow": (180, 0, 255, 180),  # Purple with transparency
    "username_text": (220, 210, 255, 255)  # Subtle lavender-white
}

_fonts_cache = {}


# === LOAD FONTS ===
def _load_fonts():
    if _fonts_cache:
        return _fonts_cache
    
    try:
        _fonts_cache["pnl"] = ImageFont.truetype(str(FONTS["pnl"]), FONT_SIZES["pnl"])
        _fonts_cache["header"] = ImageFont.truetype(str(FONTS["text"]), FONT_SIZES["header"])
        _fonts_cache["price"] = ImageFont.truetype(str(FONTS["text"]), FONT_SIZES["price"])
        _fonts_cache["username"] = ImageFont.truetype(str(FONTS["text"]), FONT_SIZES["username"])
        logger.info("Fonts loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load custom fonts, using defaults: {e}")
        for key in ["pnl", "header", "price", "username"]:
            _fonts_cache[key] = ImageFont.load_default()
    
    return _fonts_cache


# === CALCULATE PNL ===
def calculate_pnl(entry_price: float, mark_price: float, leverage: int, side: str) -> float:
    if side.upper() == "BUY":
        price_change = (mark_price - entry_price) / entry_price
    else:
        price_change = (entry_price - mark_price) / entry_price
    return price_change * leverage * 100


# === MAIN GENERATOR ===
async def generate_pnl_card(
    side: str,
    symbol: str,
    entry_price: float,
    mark_price: float,
    leverage: int,
    template_index: int = None,
    username: str = None
) -> io.BytesIO:
    """
    Generates final card based on correct template, coordinates, and color.
    """
    try:
        fonts = _load_fonts()
        
        # Pick correct template
        templates = TEMPLATES[side.upper()]
        if template_index is not None and 0 <= template_index < len(templates):
            template_path = templates[template_index]
        else:
            template_path = random.choice(templates)
        
        template_name = template_path.name
        config = TEMPLATE_CONFIGS.get(template_name)
        positions = config["positions"]
        anchors = config["anchors"]
        pnl_color = config["pnl_color"]
        
        # Load template
        img = Image.open(template_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        # Calculate PnL
        pnl_percentage = calculate_pnl(entry_price, mark_price, leverage, side)
        
        # Prepare text
        pnl_text = f"{pnl_percentage:,.2f}%"
        entry_text = f"{entry_price:,.2f}"
        mark_text = f"{mark_price:,.2f}"
        leverage_text = f"{leverage}X"
        symbol = symbol.upper()
        
        # Draw all text with proper anchors
        draw.text(
            positions["symbol"],
            symbol,
            font=fonts["header"],
            fill=COLORS["soft_grey"],
            anchor=anchors["symbol"]
        )
        
        draw.text(
            positions["leverage"],
            leverage_text,
            font=fonts["header"],
            fill=COLORS["soft_grey"],
            anchor=anchors["leverage"]
        )
        
        pnl_bbox = draw.textbbox((0, 0), pnl_text, font=fonts["pnl"])
        pnl_width = pnl_bbox[2] - pnl_bbox[0]

        # Shift position left by half the text width to center it
        centered_x = positions["pnl_percentage"][0] - (pnl_width // 2)
        centered_pos = (centered_x, positions["pnl_percentage"][1])

        draw.text(
            centered_pos,
            pnl_text,
            font=fonts["pnl"],
            fill=pnl_color,
            anchor="lt"  
)
        
        draw.text(
            positions["entry_price"],
            entry_text,
            font=fonts["price"],
            fill=COLORS["soft_grey"],
            anchor=anchors["entry_price"]
        )
        
        draw.text(
            positions["mark_price"],
            mark_text,
            font=fonts["price"],
            fill=COLORS["soft_grey"],
            anchor=anchors["mark_price"]
        )
        
        # Username label with subtle glow effect
        # todo make color of username in config other than hardcoding this
        if username:
            uname_text = f"@{username}"
            username_pos = positions["username"]

            # Pick outline color based on template style
            if "_2" in template_name:  # Purple templates
                outer_color = (180, 0, 255, 255)   # 🟣 purple glow
                inner_outline = (70, 0, 120, 255)  # darker purple edge
            else:  # Red templates
                outer_color = (220, 20, 60, 255)   # 🔴 red glow
                inner_outline = (100, 0, 0, 255)   # darker red edge

            # Outer colored outline
            for offset_x in [-3, 0, 3]:
                for offset_y in [-3, 0, 3]:
                    if offset_x != 0 or offset_y != 0:
                        draw.text(
                            (username_pos[0] + offset_x, username_pos[1] + offset_y),
                            uname_text,
                            font=fonts["username"],
                            fill=outer_color,
                            anchor=anchors["username"]
                        )

            # Inner dark outline (contrast border)
            for offset_x in [-1, 0, 1]:
                for offset_y in [-1, 0, 1]:
                    if offset_x != 0 or offset_y != 0:
                        draw.text(
                            (username_pos[0] + offset_x, username_pos[1] + offset_y),
                            uname_text,
                            font=fonts["username"],
                            fill=inner_outline,
                            anchor=anchors["username"]
                        )

            # Main white text
            draw.text(
                username_pos,
                uname_text,
                font=fonts["username"],
                fill=(255, 255, 255, 255),
                anchor=anchors["username"]
            )

        
        # Export
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        logger.error(f"Failed to generate PnL card: {e}", exc_info=True)
        return None