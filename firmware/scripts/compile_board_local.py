"""Compile the configured Freenove board when CMake's glob verification stalls.

Uses the existing ESP-IDF compile database; does not change build configuration.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


root = Path(__file__).resolve().parents[1]
build = root / "build"
entries = json.loads((build / "compile_commands.json").read_text())
compiler = None
for source in (
    "freenove-esp32s3-display-2.8-lcd.cc",
    "/main/boards/common/wifi_board.cc",
    "/main/application.cc",
    "/main/ota.cc",
    "/managed_components/78__esp-wifi-connect/wifi_manager.cc",
    "/managed_components/78__esp-wifi-connect/wifi_configuration_ap.cc",
):
    entry = next(item for item in entries if item["file"].replace("\\", "/").endswith(source))
    compiler, arguments = entry["command"].split(" ", 1)
    arguments = re.sub(r'\\(?!")', "/", arguments)
    with tempfile.NamedTemporaryFile("w", suffix=".rsp", delete=False) as response:
        response.write(arguments)
        response_path = response.name
    try:
        subprocess.run([compiler, "@" + response_path], cwd=entry["directory"], check=True)
    finally:
        os.unlink(response_path)

# Ninja normally writes these response files before running the archive/link
# commands. Recreate them from the already configured build graph.
lines = (build / "build.ninja").read_text().splitlines()
toolchain = Path(compiler).parent

# Rebuild the Wi-Fi component archive too. The exact-SSID option crosses the
# board/component boundary and must be verified even in this no-reconfigure path.
wifi_archive_line = next(
    line for line in lines
    if line.startswith("build esp-idf/78__esp-wifi-connect/lib78__esp-wifi-connect.a:")
)
wifi_objects = [
    token for token in wifi_archive_line.split("||", 1)[0].split() if token.endswith(".obj")
]
assert wifi_objects and all((build / obj).exists() for obj in wifi_objects)
wifi_response = build / "CMakeFiles" / "__idf_78__esp-wifi-connect.rsp"
wifi_response.write_text(" ".join(wifi_objects))
wifi_archive = build / "esp-idf" / "78__esp-wifi-connect" / "lib78__esp-wifi-connect.a"
wifi_archive.unlink(missing_ok=True)
subprocess.run([str(toolchain / "xtensa-esp32s3-elf-ar.exe"), "qc", str(wifi_archive),
                "@" + str(wifi_response)], cwd=build, check=True)
subprocess.run([str(toolchain / "xtensa-esp32s3-elf-ranlib.exe"), str(wifi_archive)],
               cwd=build, check=True)

archive_line = next(line for line in lines if line.startswith("build esp-idf/main/libmain.a:"))
objects = [token for token in archive_line.split("||", 1)[0].split() if token.endswith(".obj")]
assert objects and all((build / obj).exists() for obj in objects)

# The fallback build graph may predate newly embedded board artwork. Generate
# and assemble those blobs explicitly so this script still verifies a complete
# firmware image when CMake configuration is unavailable on Windows.
cmake = Path("C:/Espressif/tools/cmake/3.30.2/bin/cmake.exe")
embed_script = Path("C:/Espressif/frameworks/esp-idf-v5.5.3/tools/cmake/scripts/data_file_embed_asm.cmake")
embedded_assets = sorted((root / "main").glob("mochi_*.gif"))
embedded_assets.append(root / "main" / "wisio_loading_bg.png")
for asset in embedded_assets:
    assembly = build / f"{asset.name}.S"
    embedded_object = build / "esp-idf" / "main" / "CMakeFiles" / "__idf_main.dir" / "__" / "__" / f"{asset.name}.S.obj"
    embedded_relative = str(embedded_object.relative_to(build)).replace("\\", "/")
    graph_has_object = embedded_relative in objects
    if (graph_has_object and embedded_object.exists()
            and embedded_object.stat().st_mtime >= asset.stat().st_mtime):
        continue
    embedded_object.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(cmake), f"-D DATA_FILE={asset}", f"-D SOURCE_FILE={assembly}",
        "-D FILE_TYPE=BINARY", "-P", str(embed_script),
    ], cwd=build, check=True)
    subprocess.run([compiler, "-c", str(assembly), "-o", str(embedded_object)], cwd=build, check=True)
    if not graph_has_object:
        objects.append(embedded_relative)

archive_response = build / "CMakeFiles" / "__idf_main.rsp"
archive_response.write_text(" ".join(objects))
archive = build / "esp-idf" / "main" / "libmain.a"
archive.unlink(missing_ok=True)
subprocess.run([str(toolchain / "xtensa-esp32s3-elf-ar.exe"), "qc", str(archive),
                "@" + str(archive_response)], cwd=build, check=True)
subprocess.run([str(toolchain / "xtensa-esp32s3-elf-ranlib.exe"), str(archive)],
               cwd=build, check=True)

link_index = next(i for i, line in enumerate(lines) if line.startswith("build xiaozhi.elf:"))
project_object = "CMakeFiles/xiaozhi.elf.dir/project_elf_src_esp32s3.c.obj"
assert (build / project_object).exists()
link_libraries = lines[link_index + 3].removeprefix("  LINK_LIBRARIES = ")
link_paths = lines[link_index + 4].removeprefix("  LINK_PATH = ")
link_response = build / "CMakeFiles" / "xiaozhi.elf.rsp"
link_response.write_text(f"{project_object} {link_paths} {link_libraries}")
link_commands = subprocess.check_output(
    ["C:/Espressif/tools/ninja/1.12.1/ninja.exe", "-C", str(build),
     "-t", "commands", "xiaozhi.elf"], text=True).splitlines()
subprocess.run(link_commands[-1], cwd=build, shell=True, check=True)

idf = Path("C:/Espressif/frameworks/esp-idf-v5.5.3")
python = Path("C:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe")
subprocess.run([
    str(python), str(idf / "components/esptool_py/esptool/esptool.py"),
    "--chip", "esp32s3", "elf2image", "--flash_mode", "dio",
    "--flash_freq", "80m", "--flash_size", "16MB", "--elf-sha256-offset", "0xb0",
    "--min-rev-full", "0", "--max-rev-full", "99", "-o",
    str(build / "xiaozhi.bin"), str(build / "xiaozhi.elf"),
], cwd=build, check=True)
