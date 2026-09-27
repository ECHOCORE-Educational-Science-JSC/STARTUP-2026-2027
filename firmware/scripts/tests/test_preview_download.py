"""Compile and exercise the firmware downloader with an in-memory HTTP transport."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PreviewDownloadTests(unittest.TestCase):
    def test_http_response_handling(self):
        compiler = shutil.which("g++") or "C:/Program Files/CodeBlocks/MinGW/bin/g++.exe"
        if not Path(compiler).exists():
            self.skipTest("Host C++ compiler unavailable")
        implementation = '#include "preview_download.h"\n'
        call = 'DownloadPreviewImage(http, "https://example.test/image")'
        harness = r'''
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
struct FakeHttp {
    std::vector<uint8_t> body;
    size_t declared = 0, offset = 0;
    int opens = 0, closes = 0, status = 200;
    bool redirect = false, loop = false, error = false;
    std::string location = "/final.png";
    std::string last_url;
    void SetTimeout(int) {}
    void SetHeader(const std::string&, const std::string&) {}
    bool Open(const std::string&, const std::string& url) { last_url = url; ++opens; offset = 0; return true; }
    void Close() { ++closes; }
    int GetStatusCode() { return loop || (redirect && opens == 1) ? 302 : status; }
    size_t GetBodyLength() { return declared; }
    std::string GetResponseHeader(const std::string& key) const {
        return key == "location" ? location : "";
    }
    int Read(char* out, size_t n) {
        if (error) return -1;
        n = std::min({n, body.size() - offset, size_t(7)});
        memcpy(out, body.data() + offset, n); offset += n; return int(n);
    }
};
IMPLEMENTATION
int main() {
    std::vector<uint8_t> png = {137,80,78,71,13,10,26,10}; png.resize(32, 0);
    int failures = 0;
    auto check = [&](std::string name, FakeHttp http, bool succeeds) {
        bool success = false;
        try { auto bytes = DOWNLOAD; success = bytes == http.body; }
        catch (const std::exception&) {}
        if (success != succeeds) { std::cerr << "FAIL " << name << '\n'; ++failures; }
        if (http.closes < http.opens) { std::cerr << "FAIL unclosed response " << name << '\n'; ++failures; }
        if (success && http.redirect && http.last_url != "https://example.test/final.png") {
            std::cerr << "FAIL redirect target " << http.last_url << '\n'; ++failures;
        }
    };
    FakeHttp http; http.body = png; http.declared = png.size();
    check("known length PNG", http, true);
    http.declared = 0; check("chunked PNG without Content-Length", http, true);
    http.redirect = true; check("relative HTTP redirect", http, true);
    http.location = "final.png"; check("path-relative HTTP redirect", http, true);
    http.location = "//example.test/final.png"; check("scheme-relative HTTP redirect", http, true);
    http.loop = true; check("redirect loop", http, false); http.loop = false;
    http.redirect = false; http.declared = png.size()+10;
    check("truncated response", http, false);
    http.declared = 0; http.body.assign(320*1024+1, 1);
    check("oversized unknown-length body", http, false);
    http.body.assign(30, 'x'); check("HTML instead of image", http, false);
    http.body.clear(); check("empty body", http, false);
    http.body = png; http.error = true; check("read failure", http, false);
    http.error = false; http.status = 404; check("HTTP error", http, false);
    http.status = 200; http.body.resize(320*1024, 0);
    check("exact size limit without Content-Length", http, true);
    http.declared = 320*1024+1; check("declared oversize", http, false);
    http.declared = 0; http.body = {255,216,255,224,0,16}; check("JPEG transport", http, true);
    return failures ? 1 : 0;
}
'''.replace("IMPLEMENTATION", implementation).replace("DOWNLOAD", call)
        with tempfile.TemporaryDirectory(prefix="preview-test-") as directory:
            source = Path(directory) / "test.cc"
            executable = Path(directory) / "test.exe"
            source.write_text(harness, encoding="utf-8")
            env = dict(os.environ)
            env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
            subprocess.run([compiler, "-std=c++17", "-I", str(ROOT / "main"),
                            str(source), "-o", str(executable)], env=env, check=True,
                           capture_output=True, text=True)
            result = subprocess.run([str(executable)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
