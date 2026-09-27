/* EchoCore uses LVGL's bundled Unscii 8 pixel font for its boot wordmark.
 * Keep this board-specific wrapper instead of changing the font selection for
 * every display. The bundled font is part of LVGL (MIT license).
 */
#define LV_FONT_UNSCII_8 1
#define lv_font_unscii_8 echocore_pixel_font
#include "../../../managed_components/lvgl__lvgl/src/font/lv_font_unscii_8.c"
