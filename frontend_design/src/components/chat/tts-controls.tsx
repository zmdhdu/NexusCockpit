/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * TTS 播放控制组件 — 挂载在每条 AI 消息下方
 *
 * 功能:
 *   - 播放/暂停切换（断点续播）
 *   - 整条重放
 *   - 终止播放
 *   - 显示当前播放进度（如 "2/5"）
 *   - 仅在当前正在播放的消息上显示高亮状态
 *
 * 使用全局播放状态机，确保同一时间只有一条消息在播放。
 */

"use client";

import { useState, useEffect } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  speakSentences,
  pausePlayback,
  resumePlayback,
  replayPlayback,
  stopPlayback,
  getPlaybackState,
  getPlaybackProgress,
  getPlaybackMessageId,
  onPlaybackStateChange,
  type PlaybackState,
} from "@/lib/tts";
import { cn } from "@/lib/utils";

interface TTSControlsProps {
  /** 关联的消息 ID */
  messageId: string;
  /** 消息文本内容 */
  content: string;
  /** 消息是否正在加载中（加载中不显示控制按钮） */
  loading?: boolean;
}

export function TTSControls({ messageId, content, loading }: TTSControlsProps) {
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [activeMessageId, setActiveMessageId] = useState("");

  useEffect(() => {
    // 注册全局播放状态监听器
    const unsubscribe = onPlaybackStateChange((state, idx, tot) => {
      setPlaybackState(state);
      setCurrentIndex(idx);
      setTotal(tot);
      setActiveMessageId(getPlaybackMessageId());
    });

    // 初始化状态
    setPlaybackState(getPlaybackState());
    const progress = getPlaybackProgress();
    setCurrentIndex(progress.currentIndex);
    setTotal(progress.total);
    setActiveMessageId(getPlaybackMessageId());

    return unsubscribe;
  }, []);

  // 不显示控制按钮的情况
  if (loading || !content || content.length < 2) {
    return null;
  }

  // 判断当前消息是否是活跃的播放消息
  const isActive = activeMessageId === messageId;
  const isPlaying = isActive && playbackState === "playing";
  const isPaused = isActive && playbackState === "paused";

  // 如果不是活跃消息且没有在播放，显示播放按钮
  const showPlayButton = !isActive || playbackState === "idle" || playbackState === "stopped";

  const handlePlayPause = () => {
    if (isPlaying) {
      pausePlayback();
    } else if (isPaused) {
      resumePlayback();
    } else {
      // 开始播放这条消息
      speakSentences(content, messageId);
    }
  };

  const handleReplay = () => {
    if (isActive) {
      replayPlayback();
    } else {
      speakSentences(content, messageId);
    }
  };

  const handleStop = () => {
    stopPlayback();
  };

  return (
    <div className="flex items-center gap-1.5 mt-1">
      {/* 播放/暂停按钮 */}
      <Button
        size="sm"
        variant="ghost"
        onClick={handlePlayPause}
        className="h-7 px-2 text-xs text-muted-foreground hover:text-primary"
        title={isPlaying ? "暂停播放" : isPaused ? "继续播放" : "播放语音"}
      >
        {isPlaying ? (
          <Pause className="h-3.5 w-3.5" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
        <span className="ml-1">{isPlaying ? "暂停" : isPaused ? "继续" : "播放"}</span>
      </Button>

      {/* 重放按钮 — 仅在活跃消息时显示 */}
      {(isPlaying || isPaused) && (
        <Button
          size="sm"
          variant="ghost"
          onClick={handleReplay}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-primary"
          title="重新播放"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
      )}

      {/* 终止按钮 — 仅在活跃消息时显示 */}
      {(isPlaying || isPaused) && (
        <Button
          size="sm"
          variant="ghost"
          onClick={handleStop}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
          title="终止播放"
        >
          <Square className="h-3.5 w-3.5" />
        </Button>
      )}

      {/* 播放进度指示器 */}
      {(isPlaying || isPaused) && total > 1 && (
        <span className="text-xs text-muted-foreground tabular-nums">
          {currentIndex + 1}/{total}
        </span>
      )}

      {/* 播放状态指示器 */}
      {isPlaying && (
        <span className="flex items-center gap-1 text-xs text-primary">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
          播放中
        </span>
      )}
      {isPaused && (
        <span className="text-xs text-amber-500">已暂停</span>
      )}
    </div>
  );
}
