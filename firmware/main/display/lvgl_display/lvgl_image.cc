#include "lvgl_image.h"
#include <cbin_font.h>

#include <esp_heap_caps.h>
#include <esp_log.h>
#include <cstring>
#include <stdexcept>
#include "jpg/jpeg_to_image.h"

#define TAG "LvglImage"


LvglRawImage::LvglRawImage(void* data, size_t size) {
    std::memset(&image_dsc_, 0, sizeof(image_dsc_));
    image_dsc_.data_size = size;
    image_dsc_.data = static_cast<uint8_t*>(data);
    image_dsc_.header.magic = LV_IMAGE_HEADER_MAGIC;
    image_dsc_.header.cf = LV_COLOR_FORMAT_RAW_ALPHA;
    image_dsc_.header.w = 0;
    image_dsc_.header.h = 0;
}

bool LvglRawImage::IsGif() const {
    auto ptr = (const uint8_t*)image_dsc_.data;
    return ptr[0] == 'G' && ptr[1] == 'I' && ptr[2] == 'F';
}

LvglCBinImage::LvglCBinImage(void* data) {
    image_dsc_ = cbin_img_dsc_create(static_cast<uint8_t*>(data));
}

LvglCBinImage::~LvglCBinImage() {
    if (image_dsc_ != nullptr) {
        cbin_img_dsc_delete(image_dsc_);
    }
}

LvglAllocatedImage::LvglAllocatedImage(void* data, size_t size) {
    std::memset(&image_dsc_, 0, sizeof(image_dsc_));
#ifndef CONFIG_IDF_TARGET_ESP32
    // The screen's LVGL configuration may only enable PNG. Use the existing
    // firmware JPEG decoder for downloaded JPEGs as well as camera previews.
    const auto* encoded = static_cast<const uint8_t*>(data);
    if (size >= 4 && encoded[0] == 0xff && encoded[1] == 0xd8 && encoded[2] == 0xff) {
        uint8_t* pixels = nullptr;
        size_t pixel_size = 0, width = 0, height = 0, stride = 0;
        if (jpeg_to_image(encoded, size, &pixels, &pixel_size, &width, &height, &stride) !=
            ESP_OK) {
            throw std::runtime_error("Cannot decode JPEG; try a baseline JPEG or PNG thumbnail");
        }
        image_dsc_.header.magic = LV_IMAGE_HEADER_MAGIC;
        image_dsc_.header.cf = LV_COLOR_FORMAT_RGB565;
        image_dsc_.header.w = width;
        image_dsc_.header.h = height;
        image_dsc_.header.stride = stride;
        image_dsc_.data = pixels;
        image_dsc_.data_size = pixel_size;
        heap_caps_free(data);
        return;
    }
#endif
    image_dsc_.data_size = size;
    image_dsc_.data = static_cast<uint8_t*>(data);

    if (lv_image_decoder_get_info(&image_dsc_, &image_dsc_.header) != LV_RESULT_OK) {
        ESP_LOGE(TAG, "Failed to get image info, data: %p size: %u", data, size);
        throw std::runtime_error("Failed to get image info");
    }
}

LvglAllocatedImage::LvglAllocatedImage(void* data, size_t size, int width, int height, int stride, int color_format) {
    std::memset(&image_dsc_, 0, sizeof(image_dsc_));
    image_dsc_.data_size = size;
    image_dsc_.data = static_cast<uint8_t*>(data);
    image_dsc_.header.magic = LV_IMAGE_HEADER_MAGIC;
    image_dsc_.header.cf = color_format;
    image_dsc_.header.w = width;
    image_dsc_.header.h = height;
    image_dsc_.header.stride = stride;
}

LvglAllocatedImage::~LvglAllocatedImage() {
    if (image_dsc_.data) {
        heap_caps_free((void*)image_dsc_.data);
        image_dsc_.data = nullptr;
    }
}
