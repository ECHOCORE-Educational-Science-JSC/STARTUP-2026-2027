#pragma once

#include <string>

namespace network_endpoint {
// No throwing conversions: persisted/OTA settings are untrusted input.
inline bool Parse(const std::string& endpoint, std::string& host, int& port) {
    host.clear();
    port = 8883;
    if (endpoint.empty())
        return false;
    for (unsigned char c : endpoint) {
        if (c <= ' ' || c == 127 || c == '/' || c == '?' || c == '#' || c == '@')
            return false;
    }
    std::string port_text;
    if (endpoint.front() == '[') {
        auto end = endpoint.find(']');
        if (end == std::string::npos || end <= 1)
            return false;
        host = endpoint.substr(1, end - 1);
        if (end + 1 < endpoint.size()) {
            if (endpoint[end + 1] != ':')
                return false;
            port_text = endpoint.substr(end + 2);
            if (port_text.empty())
                return false;
        }
    } else {
        if (endpoint.find_first_of("[]") != std::string::npos)
            return false;
        auto colon = endpoint.find(':');
        if (colon != std::string::npos && endpoint.find(':', colon + 1) == std::string::npos) {
            host = endpoint.substr(0, colon);
            port_text = endpoint.substr(colon + 1);
            if (port_text.empty())
                return false;
        } else {
            host = endpoint;
        }
    }
    if (host.empty())
        return false;
    if (!port_text.empty()) {
        int parsed = 0;
        for (char c : port_text) {
            if (c < '0' || c > '9' || parsed > (65535 - (c - '0')) / 10)
                return false;
            parsed = parsed * 10 + (c - '0');
        }
        if (parsed == 0)
            return false;
        port = parsed;
    }
    return true;
}
}  // namespace network_endpoint
