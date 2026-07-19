/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useState, useRef, useCallback, useEffect } from "react";

/**
 * 将 AudioBuffer 编码为 WAV Blob (16kHz, 16-bit, mono)
 *
 * 为什么不用 MediaRecorder 的 webm 格式？
 *   webm/opus 格式需要后端安装 ffmpeg 才能转换为 wav 供 ASR 模型识别。
 *   直接在前端录制 WAV 格式，后端无需任何转换，识别速度更快、依赖更少。
 */
function encodeWav(audioBuffer: AudioBuffer): Blob {
  const targetSampleRate = 16000;
  const numChannels = 1;

  // 获取原始音频数据
  const sourceData = audioBuffer.getChannelData(0);

  // 重采样到 16kHz（线性插值）
  let data = sourceData;
  if (audioBuffer.sampleRate !== targetSampleRate) {
    const ratio = audioBuffer.sampleRate / targetSampleRate;
    const newLength = Math.round(sourceData.length / ratio);
    data = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      const srcIndex = i * ratio;
      const srcIndexFloor = Math.floor(srcIndex);
      const srcIndexCeil = Math.min(srcIndexFloor + 1, sourceData.length - 1);
      const fraction = srcIndex - srcIndexFloor;
      data[i] = sourceData[srcIndexFloor] * (1 - fraction) + sourceData[srcIndexCeil] * fraction;
    }
  }

  // 转换为 16-bit PCM
  const pcmData = new Int16Array(data.length);
  for (let i = 0; i < data.length; i++) {
    const s = Math.max(-1, Math.min(1, data[i]));
    pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  // 构建 WAV 文件头
  const buffer = new ArrayBuffer(44 + pcmData.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  // RIFF header
  writeString(0, "RIFF");
  view.setUint32(4, 36 + pcmData.length * 2, true);
  writeString(8, "WAVE");

  // fmt chunk
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);          // chunk size
  view.setUint16(20, 1, true);           // audio format (PCM)
  view.setUint16(22, numChannels, true); // num channels
  view.setUint32(24, targetSampleRate, true); // sample rate
  view.setUint32(28, targetSampleRate * numChannels * 2, true); // byte rate
  view.setUint16(32, numChannels * 2, true); // block align
  view.setUint16(34, 16, true);          // bits per sample

  // data chunk
  writeString(36, "data");
  view.setUint32(40, pcmData.length * 2, true);

  // 写入 PCM 数据
  let offset = 44;
  for (let i = 0; i < pcmData.length; i++) {
    view.setInt16(offset, pcmData[i], true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * 音频录音 Hook — 使用 AudioContext + ScriptProcessor 录制 WAV 格式音频
 *
 * 功能:
 *   - 开始/停止录音
 *   - 返回录音 Blob（WAV 格式，16kHz/16bit/单声道，可直接上传 ASR）
 *   - 录音时长计时
 *   - 浏览器兼容性检测
 *
 * 使用场景:
 *   - 聊天窗口语音输入（录完后上传到 /asr/transcribe 转文字）
 *   - 语音助手栏语音输入
 *   - 声纹注册/验证音频采集
 */
export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 改用 state 跟踪浏览器支持情况，检测到支持后触发重渲染，
  // 避免 useRef 不触发重渲染导致首次渲染时按钮被误禁用。
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    // 浏览器兼容性检查
    if (
      typeof window !== "undefined" &&
      navigator.mediaDevices &&
      (window.AudioContext || (window as any).webkitAudioContext)
    ) {
      setSupported(true);
    }
    return () => {
      // 清理资源
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        audioContextRef.current.close();
      }
    };
  }, []);

  const startRecording = useCallback(async () => {
    if (!supported) {
      setError("当前浏览器不支持录音功能");
      return;
    }

    setError(null);
    setAudioBlob(null);
    setDuration(0);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      // 创建 AudioContext
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioContextClass();
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      // 使用 ScriptProcessorNode 采集原始 PCM 数据
      // bufferSize=4096 是延迟和性能的平衡点
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        // 复制数据（因为 inputData 的 buffer 会被复用）
        const chunk = new Float32Array(inputData.length);
        chunk.set(inputData);
        chunksRef.current.push(chunk);
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setIsRecording(true);

      // 计时器
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      if (err?.name === "NotAllowedError") {
        setError("麦克风权限被拒绝，请在浏览器设置中允许访问麦克风");
      } else if (err?.name === "NotFoundError") {
        setError("未找到麦克风设备");
      } else {
        setError(`录音启动失败: ${err?.message || "未知错误"}`);
      }
    }
  }, [supported]);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (!audioContextRef.current || !isRecording) {
        setIsRecording(false);
        resolve(null);
        return;
      }

      // 断开音频处理链
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      if (sourceRef.current) {
        sourceRef.current.disconnect();
        sourceRef.current = null;
      }

      // 停止音轨
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
      }

      // 合并所有 chunk
      const chunks = chunksRef.current;
      if (chunks.length === 0) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        setIsRecording(false);
        resolve(null);
        return;
      }

      const totalLength = chunks.reduce((acc, c) => acc + c.length, 0);
      const merged = new Float32Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      // 创建 AudioBuffer 并编码为 WAV
      const audioContext = audioContextRef.current;
      const audioBuffer = audioContext.createBuffer(1, merged.length, audioContext.sampleRate);
      audioBuffer.getChannelData(0).set(merged);

      const wavBlob = encodeWav(audioBuffer);
      setAudioBlob(wavBlob);

      // 关闭 AudioContext
      audioContext.close();
      audioContextRef.current = null;

      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setIsRecording(false);
      resolve(wavBlob);
    });
  }, [isRecording]);

  const cancelRecording = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRecording(false);
    setDuration(0);
    setAudioBlob(null);
    chunksRef.current = [];
  }, []);

  const reset = useCallback(() => {
    setAudioBlob(null);
    setDuration(0);
    setError(null);
  }, []);

  return {
    isRecording,
    duration,
    error,
    audioBlob,
    supported,
    startRecording,
    stopRecording,
    cancelRecording,
    reset,
  };
}
