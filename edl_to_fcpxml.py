#!/usr/bin/env python3
"""
EDL to FCPXML Converter — 将剪辑决策列表(EDL)转为Final Cut Pro可导入的FCPXML粗剪项目。

使用方式:
    python3 edl_to_fcpxml.py \
        --source /path/to/source.mp4 \
        --edl /path/to/edl.json \
        --output /path/to/output.fcpxml \
        [--project-name "我的项目"] \
        [--gap-frames 2]

EDL JSON格式:
    [
        {"start": 4.75, "end": 7.37, "label": "你好欢迎来到老杨读红楼"},
        {"start": 8.21, "end": 12.25, "label": "很多人听说AI红楼第一个问题往往是"},
        ...
    ]

FCPX XML注意事项（踩坑记录）:
  - asset元素不能有frameDuration/width/height，用format="r1"引用format定义
  - format属性放在asset-clip上，不要放在project或sequence上
  - 文件路径必须是FCPX能访问的本地路径
  - 所有时间值用 帧数/帧率 格式（如 142/30s），确保帧对齐
  - audioChannels必须与实际音轨一致（ffprobe查）
"""

import json
import os
import sys
import argparse
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


def probe_video(path: str) -> dict:
    """用ffprobe获取视频元数据"""
    result = subprocess.run(
        ['ffprobe', '-v', 'error',
         '-show_entries', 'stream=codec_type,width,height,r_frame_rate,sample_rate,channels',
         '-show_entries', 'format=duration',
         '-of', 'json', path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe失败: {result.stderr}")

    probe = json.loads(result.stdout)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)

    # 解析帧率
    fps_parts = video['r_frame_rate'].split('/')
    fps_num, fps_den = int(fps_parts[0]), int(fps_parts[1])
    fps = fps_num / fps_den

    return {
        'width': video['width'],
        'height': video['height'],
        'fps': fps,
        'fps_num': fps_num,
        'fps_den': fps_den,
        'duration': float(probe['format']['duration']),
        'sample_rate': int(audio['sample_rate']) if audio else 48000,
        'channels': int(audio['channels']) if audio else 1,
    }


def sec_to_frame(s: float, fps: float) -> int:
    """秒转帧号（四舍五入到最近帧）"""
    return round(s * fps)


def frame_to_fcpxml(frames: int, fps_num: int, fps_den: int) -> str:
    """帧号转FCPXML时间字符串"""
    if fps_den == 1:
        return f"{frames}/{fps_num}s"
    else:
        return f"{frames * fps_num}/{fps_den}s"


def generate_fcpxml(source_path: str, edl: list, project_name: str,
                    video_info: dict, gap_frames: int = 2) -> str:
    """生成FCPXML内容"""

    fps = video_info['fps']
    fps_num = video_info['fps_num']
    fps_den = video_info['fps_den']

    def s2f(s):
        return frame_to_fcpxml(sec_to_frame(s, fps), fps_num, fps_den)

    # 计算时间线布局
    clips = []
    offset_frames = 0

    for i, entry in enumerate(edl):
        start_f = sec_to_frame(entry['start'], fps)
        end_f = sec_to_frame(entry['end'], fps)
        dur_f = end_f - start_f
        label = entry.get('label', f'Clip {i+1}')

        clips.append({
            'label': label,
            'start': frame_to_fcpxml(start_f, fps_num, fps_den),
            'duration': frame_to_fcpxml(dur_f, fps_num, fps_den),
            'offset': frame_to_fcpxml(offset_frames, fps_num, fps_den),
        })
        offset_frames += dur_f + gap_frames

    total_frames = offset_frames - gap_frames
    total_sec = total_frames / fps

    # 构建FCPXML
    # 格式定义
    if fps_den == 1:
        frame_duration = f"1/{fps_num}s"
    else:
        frame_duration = f"{fps_den}/{fps_num}s"

    src_name = os.path.basename(source_path)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE fcpxml>',
        '<fcpxml version="1.8">',
        '  <resources>',
        f'    <format id="r1" frameDuration="{frame_duration}" '
        f'width="{video_info["width"]}" height="{video_info["height"]}"/>',
        f'    <asset id="r2" name="{escape(src_name)}" '
        f'src="file://{source_path}" '
        f'start="0s" duration="{s2f(video_info["duration"])}" '
        f'hasVideo="1" hasAudio="1" '
        f'audioSources="1" audioChannels="{video_info["channels"]}" '
        f'audioRate="{video_info["sample_rate"]}.0" format="r1"/>',
        '  </resources>',
        '  <library>',
        '    <event name="AI粗剪">',
        f'      <project name="{escape(project_name)}" uid="proj-001">',
        f'        <sequence duration="{frame_to_fcpxml(total_frames, fps_num, fps_den)}">',
        '          <spine>',
    ]

    for c in clips:
        lines.append(
            f'            <asset-clip ref="r2" name="{escape(c["label"])}" '
            f'offset="{c["offset"]}" start="{c["start"]}" '
            f'duration="{c["duration"]}" format="r1" audioRole="dialogue"/>'
        )

    lines.extend([
        '          </spine>',
        '        </sequence>',
        '      </project>',
        '    </event>',
        '  </library>',
        '</fcpxml>',
    ])

    xml_content = '\n'.join(lines)

    # 验证XML格式
    try:
        ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise RuntimeError(f"生成的XML格式错误: {e}")

    return xml_content, len(clips), total_sec


def main():
    parser = argparse.ArgumentParser(
        description='EDL to FCPXML Converter — 将剪辑决策列表转为FCP粗剪项目')
    parser.add_argument('--source', required=True, help='源视频文件路径')
    parser.add_argument('--edl', required=True, help='EDL JSON文件路径')
    parser.add_argument('--output', required=True, help='输出FCPXML文件路径')
    parser.add_argument('--project-name', default='AI粗剪', help='FCPX项目名称')
    parser.add_argument('--gap-frames', type=int, default=2,
                        help='clip之间的间隔帧数（默认2帧≈67ms@30fps）')
    parser.add_argument('--fcpx-path', default=None,
                        help='FCPX端源文件路径（如与source不同，如SMB映射路径）')
    args = parser.parse_args()

    # 读EDL
    with open(args.edl, 'r', encoding='utf-8') as f:
        edl = json.load(f)

    if not edl:
        print("❌ EDL为空")
        sys.exit(1)

    # 探测视频
    print(f"📹 探测视频: {args.source}")
    video_info = probe_video(args.source)
    print(f"   {video_info['width']}x{video_info['height']}, "
          f"{video_info['fps']}fps, "
          f"{video_info['duration']:.1f}s, "
          f"音频{video_info['channels']}ch/{video_info['sample_rate']}Hz")

    # FCPX端路径（可能不同于生成端）
    fcpx_source = args.fcpx_path if args.fcpx_path else args.source

    # 生成FCPXML
    print(f"🎬 生成FCPXML ({len(edl)} clips)...")
    xml_content, clip_count, total_sec = generate_fcpxml(
        source_path=fcpx_source,
        edl=edl,
        project_name=args.project_name,
        video_info=video_info,
        gap_frames=args.gap_frames,
    )

    # 写文件
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"✅ 完成: {args.output}")
    print(f"   {clip_count} clips, 时间线 {total_sec:.1f}s ({total_sec/60:.1f}min)")
    print(f"\n📋 使用方法:")
    print(f"   1. 确保源文件在: {fcpx_source}")
    print(f"   2. FCPX → 文件 → 导入 → XML...")
    print(f"   3. 选择: {args.output}")
    print(f"   4. 导入后clip名称=台词内容，可直接拖动调整入出点")


if __name__ == '__main__':
    main()
