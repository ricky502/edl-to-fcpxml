# EDL to FCPXML Converter

AI剪辑决策 → FCPX粗剪项目。把whisper word数据产出的EDL直接转成FCPX可导入的`.fcpxml`文件，在FCPX里微调后导出，省去来回改版本的时间。

## 工作流

```
原始视频 → whisper转写(word级时间戳) → AI去重/选段 → EDL JSON → 本工具 → FCPXML → FCPX微调 → 导出
```

## 使用

```bash
# 基本用法
python3 edl_to_fcpxml.py \
    --source /path/to/source.mp4 \
    --edl /path/to/edl.json \
    --output /path/to/output.fcpxml

# 源文件在不同机器上（如Mac Mini生成，MacBook用FCPX）
python3 edl_to_fcpxml.py \
    --source /Users/agents/Public/视频/source.mp4 \
    --fcpx-path /Users/ricky/Downloads/source.mp4 \
    --edl edl.json \
    --output rough-cut.fcpxml \
    --project-name "脚本7粗剪V20"
```

## EDL JSON格式

```json
[
  {"start": 4.75, "end": 7.37, "label": "你好欢迎来到老杨读红楼"},
  {"start": 8.21, "end": 12.25, "label": "很多人听说AI红楼第一个问题往往是"}
]
```

- `start`/`end`: 源视频中的秒数（会被自动帧对齐）
- `label`: clip名称（显示在FCPX时间线上，方便定位）

## FCPX导入

1. FCPX → 文件 → 导入 → XML...
2. 选择生成的 `.fcpxml` 文件
3. 导入后每个clip独立排列，clip名称=台词内容
4. 直接拖动clip边缘调整入出点

## 依赖

- Python 3.8+
- ffprobe（ffmpeg自带）

仅用于生成FCPXML，不需要任何第三方Python库。

## FCPXML坑点记录

| 坑 | 正确做法 |
|---|---------|
| asset元素不能有frameDuration/width/height | 用`format="r1"`引用format定义 |
| format属性位置错误 | 放在`asset-clip`上，不放project/sequence |
| 时间不对齐导致FCPX警告 | 所有时间用`帧数/帧率s`格式 |
| 音频channels与实际不符 | ffprobe查实际值，如实填写 |
| 文件路径FCPX访问不到 | 用`--fcpx-path`指定FCPX端本地路径 |
