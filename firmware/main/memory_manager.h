#ifndef MEMORY_MANAGER_H_
#define MEMORY_MANAGER_H_

#include <cJSON.h>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

class McpServer;

struct MemoryRecord {
    uint64_t timestamp = 0;
    std::string fact;
    std::string category = "personal";
    int importance = 3;
};

class MemoryManager {
public:
    static MemoryManager& GetInstance();

    bool Initialize();
    bool IsSdCardMounted() const { return is_mounted_; }

    uint64_t GetTotalSpaceBytes() const;
    uint64_t GetFreeSpaceBytes() const;

    bool SaveMemory(const std::string& fact, const std::string& category = "personal", int importance = 3);
    std::vector<MemoryRecord> RecallMemories(const std::string& query = "", const std::string& category = "", size_t limit = 5);

    std::string GetProfileJsonString();
    bool UpdateProfile(const std::string& key, const std::string& value);

    cJSON* GetStorageInfoJson();

    void RegisterMcpTools(McpServer& mcp_server);

private:
    MemoryManager();
    ~MemoryManager();
    MemoryManager(const MemoryManager&) = delete;
    MemoryManager& operator=(const MemoryManager&) = delete;

    void EnsureDirectoryExists(const char* path);
    void LoadMemoriesCache();
    void FlushMemories();
    void LoadProfile();
    void FlushProfile();

    mutable std::mutex mutex_;
    bool is_mounted_ = false;
    void* card_handle_ = nullptr;
    std::vector<MemoryRecord> memories_cache_;
    cJSON* profile_json_ = nullptr;
};

#endif  // MEMORY_MANAGER_H_
