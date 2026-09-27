#include "memory_manager.h"
#include "mcp_server.h"

#include <esp_log.h>
#include <esp_timer.h>
#include <esp_vfs_fat.h>
#include <sys/stat.h>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>

#if defined(CONFIG_BOARD_TYPE_Freenove_ESP32S3_DISPLAY_2_8_LCD) || defined(CONFIG_BOARD_TYPE_ESP32_P4_FUNCTION_EV_BOARD)
#define ENABLE_SDMMC_STORAGE 1
#include <driver/sdmmc_host.h>
#include <sdmmc_cmd.h>
#endif

#define TAG "MemoryManager"

static const char* kSdMountPoint = "/sdcard";
static const char* kWisioDir = "/sdcard/wisio";
static const char* kMemoriesPath = "/sdcard/wisio/memories.json";
static const char* kProfilePath = "/sdcard/wisio/profile.json";

static std::string ToLower(const std::string& str) {
    std::string res = str;
    std::transform(res.begin(), res.end(), res.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return res;
}

MemoryManager& MemoryManager::GetInstance() {
    static MemoryManager instance;
    return instance;
}

MemoryManager::MemoryManager() {
    profile_json_ = cJSON_CreateObject();
    cJSON_AddStringToObject(profile_json_, "device", "Wisio EchoCore");
    cJSON_AddStringToObject(profile_json_, "role", "AI Companion");
}

MemoryManager::~MemoryManager() {
    if (profile_json_ != nullptr) {
        cJSON_Delete(profile_json_);
        profile_json_ = nullptr;
    }
}

void MemoryManager::EnsureDirectoryExists(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) {
        mkdir(path, 0755);
    }
}

bool MemoryManager::Initialize() {
    std::lock_guard<std::mutex> lock(mutex_);

#if defined(ENABLE_SDMMC_STORAGE) && defined(CONFIG_BOARD_TYPE_Freenove_ESP32S3_DISPLAY_2_8_LCD)
    ESP_LOGI(TAG, "Initializing SD card in 1-bit SDMMC mode (CLK:38, CMD:40, D0:39)");

    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.max_freq_khz = SDMMC_FREQ_DEFAULT;
    host.slot = SDMMC_HOST_SLOT_1;

    sdmmc_slot_config_t slot_config = SDMMC_SLOT_CONFIG_DEFAULT();
    slot_config.width = 1;
#if SOC_SDMMC_USE_GPIO_MATRIX
    slot_config.clk = static_cast<gpio_num_t>(38);
    slot_config.cmd = static_cast<gpio_num_t>(40);
    slot_config.d0 = static_cast<gpio_num_t>(39);
#endif
    slot_config.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = false,
        .max_files = 5,
        .allocation_unit_size = 16 * 1024,
        .disk_status_check_enable = false};

    sdmmc_card_t* card = nullptr;
    esp_err_t ret =
        esp_vfs_fat_sdmmc_mount(kSdMountPoint, &host, &slot_config, &mount_config, &card);
    if (ret == ESP_OK) {
        is_mounted_ = true;
        card_handle_ = card;
        uint64_t cap_mb = ((uint64_t)card->csd.capacity) * card->csd.sector_size / (1024 * 1024);
        ESP_LOGI(TAG, "SD Card mounted successfully! Capacity: %llu MB", cap_mb);
        EnsureDirectoryExists(kWisioDir);
    } else {
        ESP_LOGW(TAG, "SD Card mount skipped or failed (%s). Falling back to RAM memory cache.",
                 esp_err_to_name(ret));
        is_mounted_ = false;
    }
#else
    ESP_LOGI(TAG, "SDMMC hardware not enabled for this board target, using RAM memory cache.");
    is_mounted_ = false;
#endif

    if (is_mounted_) {
        LoadMemoriesCache();
        LoadProfile();
    }
    return is_mounted_;
}

void MemoryManager::LoadMemoriesCache() {
    memories_cache_.clear();
    FILE* f = fopen(kMemoriesPath, "r");
    if (f == nullptr) {
        ESP_LOGI(TAG, "No existing memories file found, starting fresh.");
        FlushMemories();
        return;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size <= 0 || size > 2 * 1024 * 1024) {
        fclose(f);
        return;
    }

    char* buf = static_cast<char*>(malloc(size + 1));
    if (buf == nullptr) {
        fclose(f);
        return;
    }

    size_t read_bytes = fread(buf, 1, size, f);
    buf[read_bytes] = '\0';
    fclose(f);

    cJSON* root = cJSON_Parse(buf);
    free(buf);

    if (root != nullptr && cJSON_IsArray(root)) {
        int count = cJSON_GetArraySize(root);
        for (int i = 0; i < count; i++) {
            cJSON* item = cJSON_GetArrayItem(root, i);
            if (cJSON_IsObject(item)) {
                MemoryRecord rec;
                cJSON* ts = cJSON_GetObjectItem(item, "timestamp");
                cJSON* fact = cJSON_GetObjectItem(item, "fact");
                cJSON* cat = cJSON_GetObjectItem(item, "category");
                cJSON* imp = cJSON_GetObjectItem(item, "importance");

                if (ts && cJSON_IsNumber(ts)) rec.timestamp = static_cast<uint64_t>(ts->valuedouble);
                if (fact && cJSON_IsString(fact)) rec.fact = fact->valuestring;
                if (cat && cJSON_IsString(cat)) rec.category = cat->valuestring;
                if (imp && cJSON_IsNumber(imp)) rec.importance = imp->valueint;

                if (!rec.fact.empty()) {
                    memories_cache_.push_back(rec);
                }
            }
        }
        ESP_LOGI(TAG, "Loaded %zu memories from SD card.", memories_cache_.size());
    }
    if (root != nullptr) {
        cJSON_Delete(root);
    }
}

void MemoryManager::FlushMemories() {
    if (!is_mounted_) return;

    cJSON* root = cJSON_CreateArray();
    for (const auto& rec : memories_cache_) {
        cJSON* item = cJSON_CreateObject();
        cJSON_AddNumberToObject(item, "timestamp", static_cast<double>(rec.timestamp));
        cJSON_AddStringToObject(item, "fact", rec.fact.c_str());
        cJSON_AddStringToObject(item, "category", rec.category.c_str());
        cJSON_AddNumberToObject(item, "importance", rec.importance);
        cJSON_AddItemToArray(root, item);
    }

    char* json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (json_str != nullptr) {
        std::string tmp_path = std::string(kMemoriesPath) + ".tmp";
        FILE* f = fopen(tmp_path.c_str(), "w");
        if (f != nullptr) {
            fputs(json_str, f);
            fclose(f);
            rename(tmp_path.c_str(), kMemoriesPath);
        }
        cJSON_free(json_str);
    }
}

void MemoryManager::LoadProfile() {
    FILE* f = fopen(kProfilePath, "r");
    if (f == nullptr) {
        FlushProfile();
        return;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size <= 0 || size > 64 * 1024) {
        fclose(f);
        return;
    }

    char* buf = static_cast<char*>(malloc(size + 1));
    if (buf == nullptr) {
        fclose(f);
        return;
    }

    size_t read_bytes = fread(buf, 1, size, f);
    buf[read_bytes] = '\0';
    fclose(f);

    cJSON* root = cJSON_Parse(buf);
    free(buf);

    if (root != nullptr && cJSON_IsObject(root)) {
        if (profile_json_ != nullptr) {
            cJSON_Delete(profile_json_);
        }
        profile_json_ = root;
        ESP_LOGI(TAG, "Loaded user profile from SD card.");
    }
}

void MemoryManager::FlushProfile() {
    if (!is_mounted_ || profile_json_ == nullptr) return;

    char* json_str = cJSON_Print(profile_json_);
    if (json_str != nullptr) {
        std::string tmp_path = std::string(kProfilePath) + ".tmp";
        FILE* f = fopen(tmp_path.c_str(), "w");
        if (f != nullptr) {
            fputs(json_str, f);
            fclose(f);
            rename(tmp_path.c_str(), kProfilePath);
        }
        cJSON_free(json_str);
    }
}

uint64_t MemoryManager::GetTotalSpaceBytes() const {
    if (!is_mounted_) return 0;
    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    esp_vfs_fat_info(kSdMountPoint, &total_bytes, &free_bytes);
    return total_bytes;
}

uint64_t MemoryManager::GetFreeSpaceBytes() const {
    if (!is_mounted_) return 0;
    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    esp_vfs_fat_info(kSdMountPoint, &total_bytes, &free_bytes);
    return free_bytes;
}

bool MemoryManager::SaveMemory(const std::string& fact, const std::string& category, int importance) {
    if (fact.empty()) return false;

    std::lock_guard<std::mutex> lock(mutex_);
    MemoryRecord record;
    record.timestamp = esp_timer_get_time() / 1000000ULL;
    record.fact = fact;
    record.category = category.empty() ? "personal" : category;
    record.importance = std::clamp(importance, 1, 5);

    memories_cache_.push_back(record);
    FlushMemories();
    ESP_LOGI(TAG, "Saved new memory: [%s] (importance %d) %s", record.category.c_str(),
             record.importance, record.fact.c_str());
    return true;
}

std::vector<MemoryRecord> MemoryManager::RecallMemories(const std::string& query,
                                                       const std::string& category,
                                                       size_t limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<MemoryRecord> results;
    std::string q_lower = ToLower(query);
    std::string cat_lower = ToLower(category);

    for (auto it = memories_cache_.rbegin(); it != memories_cache_.rend(); ++it) {
        if (!cat_lower.empty() && ToLower(it->category) != cat_lower) {
            continue;
        }
        if (!q_lower.empty() && ToLower(it->fact).find(q_lower) == std::string::npos) {
            continue;
        }
        results.push_back(*it);
        if (results.size() >= limit) {
            break;
        }
    }
    return results;
}

std::string MemoryManager::GetProfileJsonString() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (profile_json_ == nullptr) return "{}";
    char* str = cJSON_PrintUnformatted(profile_json_);
    std::string result(str ? str : "{}");
    if (str != nullptr) cJSON_free(str);
    return result;
}

bool MemoryManager::UpdateProfile(const std::string& key, const std::string& value) {
    if (key.empty()) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    if (profile_json_ == nullptr) {
        profile_json_ = cJSON_CreateObject();
    }
    cJSON_DeleteItemFromObject(profile_json_, key.c_str());
    cJSON_AddStringToObject(profile_json_, key.c_str(), value.c_str());
    FlushProfile();
    return true;
}

cJSON* MemoryManager::GetStorageInfoJson() {
    std::lock_guard<std::mutex> lock(mutex_);
    cJSON* json = cJSON_CreateObject();
    cJSON_AddBoolToObject(json, "sd_card_mounted", is_mounted_);
    uint64_t total_bytes = GetTotalSpaceBytes();
    uint64_t free_bytes = GetFreeSpaceBytes();
    cJSON_AddNumberToObject(json, "total_mb", static_cast<double>(total_bytes / (1024 * 1024)));
    cJSON_AddNumberToObject(json, "free_mb", static_cast<double>(free_bytes / (1024 * 1024)));
    cJSON_AddNumberToObject(json, "memory_count", static_cast<double>(memories_cache_.size()));
    return json;
}

void MemoryManager::RegisterMcpTools(McpServer& mcp_server) {
    mcp_server.AddTool(
        "self.memory.save",
        "Lưu ký ức, thông tin cá nhân, sở thích hoặc sự kiện của người dùng vào thẻ nhớ SD dài hạn (8GB/16GB).\n"
        "Hãy chủ động gọi công cụ này khi người dùng chia sẻ tên, thói quen, gia đình, sở thích, mục tiêu học tập.",
        PropertyList({
            Property("fact", kPropertyTypeString),
            Property("category", kPropertyTypeString, std::string("personal")),
            Property("importance", kPropertyTypeInteger, 3, 1, 5),
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            auto fact = properties["fact"].value<std::string>();
            std::string cat = properties.HasProperty("category")
                                  ? properties["category"].value<std::string>()
                                  : "personal";
            int imp = properties.HasProperty("importance")
                          ? properties["importance"].value<int>()
                          : 3;
            bool ok = SaveMemory(fact, cat, imp);
            cJSON* resp = cJSON_CreateObject();
            cJSON_AddBoolToObject(resp, "success", ok);
            cJSON_AddStringToObject(resp, "storage", is_mounted_ ? "sdcard" : "ram");
            cJSON_AddNumberToObject(resp, "total_memories", memories_cache_.size());
            return resp;
        });

    mcp_server.AddTool(
        "self.memory.recall",
        "Tìm kiếm và nhớ lại các ký ức đã lưu trong thẻ nhớ SD theo từ khóa hoặc chủ đề để chủ động gợi chuyện, tạo sự thân thiết.",
        PropertyList({
            Property("query", kPropertyTypeString, std::string("")),
            Property("category", kPropertyTypeString, std::string("")),
            Property("limit", kPropertyTypeInteger, 5, 1, 50),
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            std::string query = properties.HasProperty("query")
                                    ? properties["query"].value<std::string>()
                                    : "";
            std::string cat = properties.HasProperty("category")
                                  ? properties["category"].value<std::string>()
                                  : "";
            int limit = properties.HasProperty("limit")
                            ? properties["limit"].value<int>()
                            : 5;
            auto memories = RecallMemories(query, cat, limit);
            cJSON* arr = cJSON_CreateArray();
            for (const auto& m : memories) {
                cJSON* obj = cJSON_CreateObject();
                cJSON_AddStringToObject(obj, "fact", m.fact.c_str());
                cJSON_AddStringToObject(obj, "category", m.category.c_str());
                cJSON_AddNumberToObject(obj, "importance", m.importance);
                cJSON_AddItemToArray(arr, obj);
            }
            return arr;
        });

    mcp_server.AddTool(
        "self.memory.get_profile",
        "Lấy thông tin hồ sơ người dùng và thống kê ký ức được lưu trong thẻ nhớ SD.",
        PropertyList(),
        [this](const PropertyList& properties) -> ReturnValue {
            return GetStorageInfoJson();
        });

    mcp_server.AddTool(
        "self.memory.update_profile",
        "Cập nhật thông tin hồ sơ của người dùng trong thẻ nhớ (ví dụ: tên, biệt danh, sở thích, màu yêu thích).",
        PropertyList({
            Property("key", kPropertyTypeString),
            Property("value", kPropertyTypeString),
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            auto key = properties["key"].value<std::string>();
            auto val = properties["value"].value<std::string>();
            bool ok = UpdateProfile(key, val);
            cJSON* resp = cJSON_CreateObject();
            cJSON_AddBoolToObject(resp, "success", ok);
            return resp;
        });

    mcp_server.AddTool(
        "self.memory.get_storage_info",
        "Lấy thông tin chi tiết về dung lượng thẻ nhớ SD 8GB/16GB (tổng dung lượng MB, dung lượng trống MB, số ký ức).",
        PropertyList(),
        [this](const PropertyList& properties) -> ReturnValue {
            return GetStorageInfoJson();
        });
}
