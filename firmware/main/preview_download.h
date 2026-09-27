#pragma once

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

// Http::GetBodyLength() is zero for chunked responses. Read to EOF in that case,
// with the same hard limit as a response that declares Content-Length.
template <class HttpTransport>
std::vector<uint8_t> DownloadPreviewImage(HttpTransport& http, std::string url) {
    constexpr size_t kMaxBytes = 320 * 1024;
    struct CloseOnExit {
        HttpTransport& http;
        ~CloseOnExit() { http.Close(); }
    } close{http};
    http.SetTimeout(10000);
    http.SetHeader("User-Agent", "EchoCore/1.0 (educational image display)");
    http.SetHeader("Accept", "image/png,image/jpeg");
    http.SetHeader("Accept-Encoding", "identity");
    for (int redirects = 0;; ++redirects) {
        if (url.size() > 2048 || url.find_first_of("\r\n") != std::string::npos ||
            (url.rfind("https://", 0) != 0 && url.rfind("http://", 0) != 0)) {
            throw std::runtime_error("Image requires a direct HTTP or HTTPS URL");
        }
        if (!http.Open("GET", url)) {
            throw std::runtime_error("Cannot connect to image source; try another image URL");
        }
        const int status = http.GetStatusCode();
        if (status == 301 || status == 302 || status == 303 || status == 307 || status == 308) {
            auto location = http.GetResponseHeader("location");
            if (redirects >= 3 || location.empty()) {
                throw std::runtime_error("Image source has too many or invalid redirects");
            }
            const auto scheme_end = url.find("://");
            const auto path = url.find('/', scheme_end + 3);
            if (location.rfind("//", 0) == 0) {
                location = url.substr(0, scheme_end + 1) + location;
            } else if (location.front() == '/') {
                location = url.substr(0, path) + location;
            } else if (location.find("://") == std::string::npos) {
                const auto query = url.find_first_of("?#");
                const auto base = url.substr(0, query);
                location =
                    (path == std::string::npos ? base + "/" : base.substr(0, base.rfind('/') + 1)) +
                    location;
            }
            http.Close();
            url = std::move(location);
            continue;
        }
        if (status != 200) {
            throw std::runtime_error("Image source HTTP status " + std::to_string(status) +
                                     "; try another direct image URL");
        }
        break;
    }
    const size_t length = http.GetBodyLength();
    if (length > kMaxBytes) {
        throw std::runtime_error("Image exceeds 320 KiB; use a small thumbnail");
    }
    std::vector<uint8_t> bytes;
    bytes.reserve(length ? length : 4096);
    char chunk[2048];
    while (length == 0 || bytes.size() < length) {
        size_t requested =
            std::min(sizeof(chunk), length ? length - bytes.size() : kMaxBytes + 1 - bytes.size());
        const int count = http.Read(chunk, requested);
        if (count < 0 || static_cast<size_t>(count) > requested) {
            throw std::runtime_error("Image download interrupted; retry with another image URL");
        }
        if (count == 0) {
            break;
        }
        if (bytes.size() + count > kMaxBytes) {
            throw std::runtime_error("Image exceeds 320 KiB; use a small thumbnail");
        }
        if (bytes.size() + count > bytes.capacity()) {
            bytes.reserve(
                std::min(kMaxBytes, std::max(bytes.size() + count, bytes.capacity() * 2)));
        }
        bytes.insert(bytes.end(), chunk, chunk + count);
    }
    if (bytes.empty() || (length != 0 && bytes.size() != length)) {
        throw std::runtime_error("Image download is empty or incomplete");
    }
    constexpr uint8_t png[] = {137, 80, 78, 71, 13, 10, 26, 10};
    const bool is_png = bytes.size() >= 24 && std::memcmp(bytes.data(), png, sizeof(png)) == 0;
    const bool is_jpeg =
        bytes.size() >= 4 && bytes[0] == 0xff && bytes[1] == 0xd8 && bytes[2] == 0xff;
    if (!is_png && !is_jpeg) {
        throw std::runtime_error("Source is not PNG/JPEG; use a direct image URL, not a web page");
    }
    return bytes;
}
