# 音频管线技术文档

> 车载音乐播放全链路技术说明

## 架构

```
后端 MockVehicleBus                      前端 vehicle-panel.tsx
  ├─ _scan_music_dir()                     ├─ audioRef (HTMLAudioElement)
  │   扫描 assets/audio/music/             │   使用 track.url 播放
  │   生成播放列表 (含 title, url)         │
  ├─ vehicle_media(op="play")              ├─ useEffect 监听 media.playing
  │   更新 self.media["track"]             │   自动播放/暂停
  └─ GET /vehicle/status                   └─ 渲染播放列表
      返回 media.track + playlist               点击切歌
```

## v2.2 修复

### 问题
1. **后端硬编码播放列表**: `MockVehicleBus.__init__` 中硬编码了 12 首歌曲名
2. **前端硬编码 URL**: `vehicle-panel.tsx` 中 URL 为 `track_01.wav` 格式
3. **前端不兼容 dict 格式**: 播放列表渲染假设为 `string[]`，但后端返回 `dict[]`

### 修复
1. **后端动态扫描**: `MockVehicleBus._scan_music_dir()` 扫描 `assets/audio/music/` 目录
2. **返回完整信息**: 每首歌包含 `title`、`filename`、`url`、`format`
3. **前端使用后端 URL**: 优先使用 `media.track.url`，兼容旧格式
4. **前端兼容 dict**: 播放列表渲染支持 `dict[]` 和 `string[]`

## 音频文件放置

将 `.mp3` 或 `.wav` 文件放入：
```
assets/audio/music/
  ├─ 王力宏-爱错.mp3
  ├─ 周杰伦 - 晴天.wav
  └─ ...
```

系统会自动扫描并生成播放列表。文件名格式：
- `歌手-歌名.mp3` → 解析为 `歌名 - 歌手`
- `歌手 - 歌名.wav` → 解析为 `歌名 - 歌手`

## 静态文件挂载

```python
# main.py
app.mount("/audio", StaticFiles(directory=_audio_dir), name="audio")
```

前端通过 `{API_URL}/audio/music/{filename}` 访问音频文件。

## 个性化音乐匹配

`PersonalizationService.match_music(user_id)` 根据用户偏好匹配歌曲：

1. 读取 `data/preferences/{user_id}.json` 中的 `music.favorite_songs`
2. 扫描本地音乐库
3. 模糊匹配用户偏好歌曲名与本地文件名
4. 无匹配时返回全部歌曲
