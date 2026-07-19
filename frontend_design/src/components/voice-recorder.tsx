/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useState, useRef, useEffect } from "react";
import { Mic, Square, Play, CheckCircle2, AlertCircle, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { useAudioRecorder } from "@/hooks/use-audio-recorder";

/**
 * 声纹录音组件
 *
 * 使用 useAudioRecorder hook 录制真正的 WAV 格式（16kHz/16bit/mono PCM）。
 *
 * 之前使用 MediaRecorder API，其在 Chrome 中默认输出 audio/webm; codecs=opus，
 * 即使把 Blob 的 MIME type 标记为 "audio/wav"，实际二进制数据仍是 webm 编码，
 * 导致后端 torchaudio.load() 报错 "Format not recognised"。
 *
 * useAudioRecorder 通过 AudioContext + ScriptProcessor 采集原始 PCM 数据，
 * 再用 encodeWav 手动构建标准 WAV 文件头，生成 torchaudio 可直接识别的 WAV。
 */
export function VoiceRecorder({
  onRecordingComplete,
}: {
  onRecordingComplete: (file: File | null) => void;
}) {
  const {
    isRecording,
    duration,
    error,
    audioBlob,
    supported,
    startRecording,
    stopRecording,
    reset,
  } = useAudioRecorder();

  const [isPlaying, setIsPlaying] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handleStart = async () => {
    // 撤销旧的 Object URL，避免内存泄漏
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setIsPlaying(false);
    // 通知父组件清除旧的录音文件
    onRecordingComplete(null);
    await startRecording();
  };

  const handleStop = async () => {
    const blob = await stopRecording();
    if (blob) {
      // 生成真正的 WAV 文件（blob 的 type 已经是 audio/wav）
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
      const file = new File([blob], "voiceprint_recording.wav", {
        type: "audio/wav",
      });
      onRecordingComplete(file);
    }
  };

  const deleteRecording = () => {
    // 撤销旧的 Object URL 防止内存泄漏
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioUrl(null);
    setIsPlaying(false);
    reset();
    // 通知父组件录音已清除
    onRecordingComplete(null);
  };

  const playAudio = () => {
    if (audioRef.current && audioUrl) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play();
        setIsPlaying(true);
      }
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  // 组件卸载或 URL 变化时清理资源
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  return (
    <div className="space-y-4">
      {(error || !supported) && (
        <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-3 text-red-400">
          <AlertCircle className="h-4 w-4" />
          <p className="text-sm">
            {error || "当前浏览器不支持录音功能"}
          </p>
        </div>
      )}

      {/* 录音控制 */}
      <div className="flex items-center gap-3 flex-wrap">
        {!isRecording ? (
          <Button
            onClick={handleStart}
            variant="outline"
            className="flex items-center gap-2"
            disabled={!supported}
          >
            <Mic className="h-4 w-4" />
            {audioBlob ? "重新录音" : "开始录音"}
          </Button>
        ) : (
          <Button
            onClick={handleStop}
            variant="destructive"
            className="flex items-center gap-2"
          >
            <Square className="h-4 w-4" />
            停止录音
          </Button>
        )}

        {audioBlob && !isRecording && (
          <>
            <Button
              onClick={playAudio}
              variant="outline"
              className="flex items-center gap-2"
            >
              {isPlaying ? (
                <Square className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {isPlaying ? "暂停" : "回放"}
            </Button>
            <Button
              onClick={deleteRecording}
              variant="ghost"
              className="flex items-center gap-2 text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
              删除
            </Button>
          </>
        )}

        {isRecording && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="flex gap-1">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="w-1 bg-primary animate-pulse"
                  style={{
                    height: `${8 + Math.sin((i + duration) * 2) * 4}px`,
                    animationDelay: `${i * 0.2}s`,
                  }}
                />
              ))}
            </div>
            <span>{formatTime(duration)}</span>
          </div>
        )}

        {audioBlob && (
          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <CheckCircle2 className="h-4 w-4" />
            <span>已录制 {formatTime(duration)}</span>
          </div>
        )}
      </div>

      {/* 隐藏的音频元素用于回放 */}
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          onEnded={() => setIsPlaying(false)}
          className="hidden"
        />
      )}

      {/* 提示信息 */}
      {!audioBlob && !isRecording && (
        <p className="text-xs text-muted-foreground">
          录音时长建议 3-10 秒，请清晰朗读您的用户名或常用短语
        </p>
      )}
    </div>
  );
}
