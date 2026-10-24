"""QR codes for listen links (PRD QR-6): error correction M or higher, 4-module quiet zone, dark on light."""
import io

import segno

DARK = "#1a1a2e"
LIGHT = "#ffffff"


def _qr(url):
    # boost_error lets segno pick a higher level than M when it fits in the same size.
    return segno.make(url, error="m", boost_error=True, micro=False)


def make_qr_svg(url, scale=8):
    buffer = io.BytesIO()
    _qr(url).save(buffer, kind="svg", scale=scale, border=4, dark=DARK, light=LIGHT, xmldecl=False)
    return buffer.getvalue().decode("utf-8")


def make_qr_png(url, scale=12):
    buffer = io.BytesIO()
    _qr(url).save(buffer, kind="png", scale=scale, border=4, dark=DARK, light=LIGHT)
    return buffer.getvalue()


def make_qr_data_uri(url, scale=8):
    """SVG data URI, for embedding in HTML that WeasyPrint renders to PDF."""
    return _qr(url).svg_data_uri(scale=scale, border=4, dark=DARK, light=LIGHT)
