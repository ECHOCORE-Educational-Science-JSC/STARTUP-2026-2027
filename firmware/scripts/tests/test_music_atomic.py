"""Exercise actual music display methods with an in-memory LVGL surface."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]


class AtomicMusicTests(unittest.TestCase):
    def _compile_run(self, harness):
        compiler = shutil.which("g++") or "C:/Program Files/CodeBlocks/MinGW/bin/g++.exe"
        if not Path(compiler).exists():
            self.skipTest("Host C++ compiler unavailable")
        temporary_root = ROOT / "test-tmp"
        temporary_root.mkdir(exist_ok=True)
        directory = temporary_root / ("music-atomic-" + uuid.uuid4().hex)
        directory.mkdir()
        try:
            source = directory / "test.cc"
            executable = directory / "test.exe"
            source.write_text(harness, encoding="utf-8")
            env = dict(os.environ)
            env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
            result = subprocess.run([compiler, "-std=c++17", "-I", str(ROOT / "main"),
                                     str(source), "-o", str(executable)], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            shutil.rmtree(directory)

    def test_optional_lvgl_atomic_api_and_start_contract(self):
        header = (ROOT / "main/display/lvgl_display/lvgl_display.h").read_text(encoding="utf-8")
        app = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        start = app.split("music_state == MusicMessageState::kStart", 1)[1].split(
            "music_state == MusicMessageState::kCover", 1)[0]
        self.assertIn("ShowMusicPlayerWithCover", header)
        self.assertIn("ShowMusicPlayerWithCover", start)
        self.assertIn("ReadMusicCover", start)
        self.assertIn("music_playback_token_ = token", start)

    def test_png_limits_and_music_states_in_native_code(self):
        self._compile_run(r'''
#include <algorithm>
#include <iostream>
#include <vector>
#include "music_message.h"
int main() {
    std::vector<uint8_t> png={137,80,78,71,13,10,26,10,0,0,0,13,'I','H','D','R',0,0,1,64,0,0,0,240};
    if(!IsMusicCoverPng(png.data(),png.size())) return 1;
    if(IsMusicCoverPng(nullptr,0) || IsMusicCoverPng(png.data(),8)) return 2;
    png[0]=0; if(IsMusicCoverPng(png.data(),png.size())) return 3; png[0]=137;
    png[12]='X'; if(IsMusicCoverPng(png.data(),png.size())) return 4; png[12]='I';
    png[16]=127; if(IsMusicCoverPng(png.data(),png.size())) return 5; png[16]=0;
    std::fill(png.begin()+16,png.begin()+20,0); if(IsMusicCoverPng(png.data(),png.size())) return 6;
    if(ParseMusicMessageState("start")!=MusicMessageState::kStart ||
       ParseMusicMessageState("cover")!=MusicMessageState::kCover ||
       ParseMusicMessageState("stop")!=MusicMessageState::kStop ||
       ParseMusicMessageState("x")!=MusicMessageState::kInvalid) return 7;
    return 0;
}
''')

    def test_actual_start_callback_preserves_same_token_screen_and_progress(self):
        app = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        start = app.split("music_state == MusicMessageState::kStart", 1)[1].split(
            "music_state == MusicMessageState::kCover", 1)[0]
        callback = start.index("Schedule([this, display,")
        brace = start.index("{", callback)
        depth, end = 1, brace + 1
        while depth:
            depth += (start[end] == "{") - (start[end] == "}")
            end += 1
        body = start[brace:end]
        harness = r'''
#include <cstdlib>
#include <cstdint>
#include <memory>
#include <string>
#include <stdexcept>
#include "audio/music_playback_clock.h"
#define ESP_LOGW(...) ((void)0)
int decodes=0, images=0;
struct LvglImage { virtual ~LvglImage()=default; };
struct LvglAllocatedImage:LvglImage {
    void* data;
    LvglAllocatedImage(void* p,size_t):data(p){++decodes; ++images;}
    ~LvglAllocatedImage(){std::free(data); --images;}
};
struct Display {
    int starts=0, updates=0; uint32_t position=0; std::string title;
    virtual ~Display()=default;
    virtual void ShowMusicPlayer(const std::string& t,const std::string&,uint32_t){++starts;title=t;position=0;}
    virtual void UpdateMusicProgress(uint32_t p,uint32_t){++updates;position=p;}
};
struct LvglDisplay:Display {
    std::unique_ptr<LvglImage> image;
    void ShowMusicPlayerWithCover(const std::string& t,const std::string& a,uint32_t d,
                                 std::unique_ptr<LvglImage> i,uint32_t){
        ShowMusicPlayer(t,a,d); image=std::move(i);
    }
};
struct DisplayLockGuard{DisplayLockGuard(Display*){}};
struct MusicCover {
    std::unique_ptr<void,decltype(&std::free)> data{nullptr,std::free};
    size_t size=1; uint32_t accent=0x123456;
};
constexpr int kDeviceStateSpeaking=7;
struct Audio {
    MusicPlaybackClock clock;
    void StartMusicPlaybackClock(){clock.Start(24000);}
    uint32_t MusicPlaybackPositionMs(){return clock.PositionMs();}
    bool mic=true,wake=true;
    void EnableVoiceProcessing(bool on){mic=on;}
    void EnableWakeWordDetection(bool on){wake=on;}
};
struct Application {
    uint32_t music_duration_ms_=0;
    bool music_playback_=false,aborted_=true; int music_idle_seconds_=9,state=0;
    std::string music_playback_token_; Audio audio_service_;
    void SetDeviceState(int s){state=s;}
    void ApplyStart(Display* display,std::string token,std::string title,std::string artist,
                    uint32_t duration_ms,bool has_position,uint32_t position_ms,
                    std::shared_ptr<MusicCover> cover)
    CALLBACK
};
int main(){
    Application app; LvglDisplay display;
    auto first=std::make_shared<MusicCover>(); first->data.reset(std::malloc(1));
    app.ApplyStart(&display,"one","Bài một","",65000,false,0,first);
    if(display.starts!=1 || app.music_playback_token_!="one" || !app.music_playback_ ||
       app.state!=kDeviceStateSpeaking || app.audio_service_.mic || app.audio_service_.wake) return 1;
#if HAVE_LVGL
    if(decodes!=1 || images!=1) return 2;
#endif
    auto repeat=std::make_shared<MusicCover>(); repeat->data.reset(std::malloc(1));
    auto epoch=app.audio_service_.clock.epoch();
    app.audio_service_.clock.Written(epoch,100800); // 4.2 seconds actually written.
    app.ApplyStart(&display,"one","Bài một","",65000,true,50000,repeat);
    if(display.starts!=1 || display.position!=4200 || display.updates!=1 ||
       display.title!="Bài một" || app.audio_service_.mic || app.audio_service_.wake) return 3;
#if HAVE_LVGL
    if(decodes!=1 || images!=1 || !repeat->data) return 4; // No repeated decode/ownership transfer.
#endif
    app.ApplyStart(&display,"one","Bài một","",65000,false,0,repeat);
    if(display.starts!=1 || display.position!=4200 || display.updates!=2 ||
       app.audio_service_.clock.epoch()!=epoch) return 5;
    auto next=std::make_shared<MusicCover>();
    app.ApplyStart(&display,"two","Bài hai","",0,false,0,next);
    if(display.starts!=2 || display.position!=0 || display.title!="Bài hai" ||
       app.music_playback_token_!="two" || app.audio_service_.MusicPlaybackPositionMs()!=0) return 6;
    return 0;
}
'''.replace("CALLBACK", body)
        for lvgl in (0, 1):
            with self.subTest(lvgl=lvgl):
                self._compile_run(f"#define HAVE_LVGL {lvgl}\n" + harness)

    def test_real_lcd_music_transition_is_complete_and_uses_one_lock(self):
        source = (ROOT / "main/display/lcd_display.cc").read_text(encoding="utf-8")
        methods = source.split("void LcdDisplay::ShowMusicPlayer(", 1)[1].split(
            "void LcdDisplay::ShowChargingScreen", 1)[0]
        methods = "void LcdDisplay::ShowMusicPlayer(" + methods
        self._compile_run(r'''
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
constexpr int LV_OBJ_FLAG_HIDDEN=1,LV_OBJ_FLAG_SCROLLABLE=2,LV_OPA_COVER=255,LV_OPA_90=230;
constexpr int LV_ALIGN_TOP_MID=1,LV_ALIGN_BOTTOM_MID=2,LV_ALIGN_CENTER=3,LV_PART_INDICATOR=1;
constexpr int LV_LABEL_LONG_SCROLL_CIRCULAR=1,LV_TEXT_ALIGN_CENTER=1,LV_SCROLLBAR_MODE_OFF=0;
constexpr int LV_ANIM_OFF=0,LV_ANIM_ON=1,LV_HOR_RES=320,LV_VER_RES=240,LV_RADIUS_CIRCLE=32767;
#define ESP_LOGW(...) ((void)0)
struct lv_img_dsc_t { struct { int w=320,h=240; } header; };
struct LvglImage { lv_img_dsc_t dsc; static int alive; LvglImage(){++alive;} virtual ~LvglImage(){--alive;}
 const lv_img_dsc_t* image_dsc() const{return &dsc;} }; int LvglImage::alive=0;
struct FakeGif { bool running=true; void Stop(){running=false;} void Start(){running=true;} };
struct lv_obj_t { bool hidden=false; int w=0,h=0,z=0,bg_opa=0,value=0,anim=-1; const lv_img_dsc_t* src=nullptr;
 std::string text; lv_obj_t* parent=nullptr; };
int layers=0; lv_obj_t screen;
lv_obj_t* lv_screen_active(){return &screen;}
lv_obj_t* create(lv_obj_t* p){auto* o=new lv_obj_t; o->parent=p; o->z=++layers; return o;}
lv_obj_t* lv_obj_create(lv_obj_t* p){return create(p);}
lv_obj_t* lv_label_create(lv_obj_t* p){return create(p);}
lv_obj_t* lv_image_create(lv_obj_t* p){return create(p);}
lv_obj_t* lv_bar_create(lv_obj_t* p){return create(p);}
void lv_obj_add_flag(lv_obj_t* o,int f){if(f==LV_OBJ_FLAG_HIDDEN)o->hidden=true;}
void lv_obj_remove_flag(lv_obj_t* o,int f){if(f==LV_OBJ_FLAG_HIDDEN)o->hidden=false;}
void lv_obj_clear_flag(lv_obj_t* o,int f){lv_obj_remove_flag(o,f);}
void lv_obj_set_size(lv_obj_t* o,int w,int h){o->w=w;o->h=h;}
void lv_obj_set_width(lv_obj_t* o,int w){o->w=w;}
void lv_obj_move_foreground(lv_obj_t* o){o->z=++layers;}
void lv_label_set_text(lv_obj_t* o,const char* s){o->text=s;}
void lv_image_set_src(lv_obj_t* o,const lv_img_dsc_t* s){o->src=s;}
void lv_obj_set_style_bg_opa(lv_obj_t* o,int a,int){o->bg_opa=a;}
int lv_color_hex(int c){return c;} int lv_color_white(){return 0xffffff;}
#define STUB(name) template<typename... A> void name(A...){ }
STUB(lv_obj_align) STUB(lv_obj_center) STUB(lv_obj_set_style_radius)
STUB(lv_obj_set_style_border_width) STUB(lv_obj_set_style_pad_all)
STUB(lv_obj_set_style_border_color)
STUB(lv_obj_set_style_bg_color) STUB(lv_obj_set_scrollbar_mode)
STUB(lv_label_set_long_mode) STUB(lv_obj_set_style_text_color)
STUB(lv_obj_set_style_text_align) STUB(lv_bar_set_range)
void lv_bar_set_value(lv_obj_t* o,int v,int a){o->value=v;o->anim=a;}
STUB(lv_image_set_scale) STUB(esp_timer_stop) STUB(lv_obj_remove_style_all)
STUB(lv_obj_set_style_outline_width) STUB(lv_obj_set_style_shadow_width)
struct LcdDisplay {
 int width_=320,height_=240,locks=0; bool music_active_=false;
 uint32_t music_accent_color_=0x38bdf8; void* preview_timer_=nullptr;
 lv_obj_t *music_cover_image_=nullptr,*music_top_panel_=nullptr,*music_bottom_panel_=nullptr;
 lv_obj_t *music_title_label_=nullptr,*music_progress_bar_=nullptr,*music_time_label_=nullptr;
 lv_obj_t *music_placeholder_=nullptr,*top_bar_=create(&screen),*bottom_bar_=create(&screen);
 lv_obj_t *preview_image_=create(&screen),*emoji_box_=create(&screen);
 std::unique_ptr<LvglImage> music_cover_cached_,preview_image_cached_;
 std::unique_ptr<FakeGif> gif_controller_=std::make_unique<FakeGif>();
 void ShowMusicPlayer(const std::string&,const std::string&,uint32_t);
 void ShowMusicPlayerWithCover(const std::string&,const std::string&,uint32_t,std::unique_ptr<LvglImage>,uint32_t);
 void ShowMusicPlayerLocked(const std::string&,const std::string&,uint32_t);
 void SetMusicCoverLocked(std::unique_ptr<LvglImage>);
 void SetMusicCover(std::unique_ptr<LvglImage>);
 void SetMusicAccentColor(uint32_t); void UpdateMusicProgress(uint32_t,uint32_t); void HideMusicPlayer();
};
struct DisplayLockGuard { LcdDisplay* d; DisplayLockGuard(LcdDisplay* p):d(p){++d->locks;} };
static void FormatMusicTime(uint32_t ms,char* out,size_t n){snprintf(out,n,"%02lu:%02lu",(unsigned long)(ms/60000),(unsigned long)(ms/1000%60));}
METHODS
bool complete(LcdDisplay& d,const std::string& title) {
 bool cover=!d.music_cover_image_->hidden && d.music_cover_image_->src;
 bool placeholder=d.music_placeholder_ && !d.music_placeholder_->hidden && d.music_placeholder_->bg_opa==255 &&
                  d.music_placeholder_->w==320 && d.music_placeholder_->h==240;
 return d.music_active_ && d.emoji_box_->hidden && d.preview_image_->hidden && !d.gif_controller_->running &&
        !d.music_top_panel_->hidden && !d.music_bottom_panel_->hidden && (cover||placeholder) &&
        d.music_title_label_->text==title &&
        d.music_top_panel_->z>(cover?d.music_cover_image_->z:d.music_placeholder_->z) &&
        d.music_bottom_panel_->z>(cover?d.music_cover_image_->z:d.music_placeholder_->z);
}
int main(){
 LcdDisplay d;
 d.ShowMusicPlayerWithCover("Bài một","",65000,std::make_unique<LvglImage>(),0x123456);
 if(!complete(d,"Bài một") || d.locks!=1 || LvglImage::alive!=1 || d.music_time_label_->text!="00:00 / 01:05") return 1;
 d.UpdateMusicProgress(5000,278000);
 if(d.music_progress_bar_->value!=17 || d.music_progress_bar_->anim!=LV_ANIM_OFF ||
    d.music_time_label_->text!="00:05 / 04:38") return 7;
 d.UpdateMusicProgress(139000,278000);
 if(d.music_progress_bar_->value!=500) return 8;
 d.UpdateMusicProgress(300000,278000);
 if(d.music_progress_bar_->value!=1000 || d.music_time_label_->text!="04:38 / 04:38") return 9;
 d.UpdateMusicProgress(5000,0);
 if(d.music_progress_bar_->value!=0 || d.music_time_label_->text!="00:05 / --:--") return 10;
 d.locks=1;
 d.ShowMusicPlayer("Bài hai","",0);
 if(!complete(d,"Bài hai") || d.locks!=2 || !d.music_cover_image_->hidden || LvglImage::alive!=0 || d.music_time_label_->text!="00:00 / --:--" || d.music_progress_bar_->value!=0) return 2;
 d.SetMusicCover(std::make_unique<LvglImage>());
 if(!complete(d,"Bài hai") || !d.music_placeholder_->hidden || LvglImage::alive!=1) return 3;
 d.HideMusicPlayer();
 if(d.music_active_ || !d.music_cover_image_->hidden || !d.music_placeholder_->hidden ||
    !d.music_top_panel_->hidden || !d.music_bottom_panel_->hidden || d.emoji_box_->hidden || LvglImage::alive!=0) return 4;
 d.SetMusicCover(std::make_unique<LvglImage>());
 if(LvglImage::alive!=0 || !d.music_cover_image_->hidden) return 5;
 auto invalid=std::make_unique<LvglImage>(); invalid->dsc.header.w=0;
 d.ShowMusicPlayerWithCover("Bài ba","",1000,std::move(invalid),0x123456);
 if(!complete(d,"Bài ba") || LvglImage::alive!=0 || !d.music_cover_image_->hidden) return 6;
 return 0;
}
'''.replace("METHODS", methods))


if __name__ == "__main__":
    unittest.main()
