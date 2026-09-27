"""Verify JPEG decoder routing and allocation ownership in the actual LVGL wrapper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PreviewJpegTests(unittest.TestCase):
    def test_decoder_routing_and_ownership(self):
        compiler = shutil.which("g++") or "C:/Program Files/CodeBlocks/MinGW/bin/g++.exe"
        if not Path(compiler).exists():
            self.skipTest("Host C++ compiler unavailable")
        stubs = {
            "sdkconfig.h": "",
            "esp_err.h": "#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n",
            "esp_log.h": '#pragma once\n#define ESP_LOGE(...) ((void)0)\n',
            "esp_heap_caps.h": '#pragma once\nvoid heap_caps_free(void*);\n',
            "lvgl.h": '''#pragma once
#include <cstddef>
#include <cstdint>
#define LV_IMAGE_HEADER_MAGIC 25
#define LV_COLOR_FORMAT_RAW_ALPHA 1
#define LV_COLOR_FORMAT_RGB565 2
#define LV_RESULT_OK 0
struct lv_image_header_t { int magic=0, cf=0, w=0, h=0, stride=0; };
struct lv_img_dsc_t { lv_image_header_t header; size_t data_size; const uint8_t* data; };
int lv_image_decoder_get_info(const lv_img_dsc_t*, lv_image_header_t*);
''',
            "cbin_font.h": '''#pragma once
#include "lvgl.h"
inline lv_img_dsc_t* cbin_img_dsc_create(uint8_t*) { return nullptr; }
inline void cbin_img_dsc_delete(lv_img_dsc_t*) {}
''',
        }
        harness = r'''
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include "lvgl_image.h"
#include "jpg/jpeg_to_image.h"
int frees=0, jpeg_calls=0; bool fail=false;
void heap_caps_free(void* p) { ++frees; free(p); }
int lv_image_decoder_get_info(const lv_img_dsc_t* d, lv_image_header_t* h) {
    if (d->data[0] != 137) return -1; // Screen configured with PNG only.
    h->w=320; h->h=240; return 0;
}
extern "C" int jpeg_to_image(const uint8_t*, size_t, uint8_t** out, size_t* n,
                             size_t* w, size_t* h, size_t* stride) {
    ++jpeg_calls; if(fail) return -1;
    *w=320; *h=240; *stride=640; *n=320*240*2;
    *out=static_cast<uint8_t*>(malloc(*n)); return 0;
}
void* jpeg() { auto p=static_cast<uint8_t*>(malloc(4)); p[0]=255;p[1]=216;p[2]=255;p[3]=224; return p; }
int main() {
    try {
        { LvglAllocatedImage image(jpeg(),4);
          if(jpeg_calls!=1 || frees!=1 || image.image_dsc()->header.cf!=LV_COLOR_FORMAT_RGB565 ||
             image.image_dsc()->header.w!=320 || image.image_dsc()->data_size!=153600) return 1; }
        if(frees!=2) return 2;
        fail=true; auto raw=jpeg(); bool rejected=false;
        try { LvglAllocatedImage image(raw,4); } catch(const std::exception&) { rejected=true; }
        if(!rejected || frees!=2) return 3; // Constructor failure leaves input with caller.
        heap_caps_free(raw);
        auto png=static_cast<uint8_t*>(malloc(32)); png[0]=137;
        { LvglAllocatedImage image(png,32); if(image.image_dsc()->data!=png || jpeg_calls!=2) return 4; }
        if(frees!=4) return 5;
    } catch(const std::exception& e) { std::cerr << e.what(); return 6; }
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="preview-jpeg-") as directory:
            temporary = Path(directory)
            for name, content in stubs.items():
                (temporary / name).write_text(content, encoding="utf-8")
            (temporary / "test.cc").write_text(harness, encoding="utf-8")
            wrapper = Path(os.environ.get("ECHOCORE_IMAGE_SOURCE", str(ROOT / "main/display/lvgl_display/lvgl_image.cc")))
            env = dict(os.environ)
            env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
            command = [compiler, "-std=c++17", "-I", str(temporary), "-I",
                       str(ROOT / "main/display/lvgl_display"), str(wrapper),
                       str(temporary / "test.cc"), "-o", str(temporary / "test.exe")]
            compiled = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(temporary / "test.exe")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
