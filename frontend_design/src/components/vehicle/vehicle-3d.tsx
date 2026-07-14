/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, ContactShadows } from "@react-three/drei";
import * as THREE from "three";
import type { Mesh } from "three";

/**
 * 3D 车辆模型组件 (v2.0)
 *
 * 使用 @react-three/fiber + @react-three/drei 程序化生成低多边形车体，
 * 无需外部 GLB/GLTF 模型文件。
 *
 * 交互: 点击车身部位（车窗/座椅/空调）高亮并发送对应车控指令
 */

// 低多边形车体
function CarBody({ highlight, onPartClick }: { highlight: string | null; onPartClick: (part: string) => void }) {
  const bodyRef = useRef<Mesh>(null);

  useFrame((state) => {
    if (bodyRef.current) {
      bodyRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.3) * 0.1;
    }
  });

  return (
    <group ref={bodyRef as any}>
      {/* 车身底盘 */}
      <mesh
        position={[0, 0.3, 0]}
        onClick={() => onPartClick("body")}
        castShadow
      >
        <boxGeometry args={[2.2, 0.5, 4]} />
        <meshStandardMaterial
          color={highlight === "body" ? "#06b6d4" : "#1e3a5f"}
          metalness={0.8}
          roughness={0.2}
        />
      </mesh>

      {/* 车顶 */}
      <mesh position={[0, 0.8, -0.2]} castShadow>
        <boxGeometry args={[1.8, 0.6, 2.2]} />
        <meshStandardMaterial
          color={highlight === "body" ? "#0e7490" : "#1e3a5f"}
          metalness={0.9}
          roughness={0.15}
        />
      </mesh>

      {/* 前挡风玻璃 */}
      <mesh
        position={[0, 0.75, 1.1]}
        rotation={[Math.PI * 0.12, 0, 0]}
        onClick={() => onPartClick("window")}
        castShadow
      >
        <boxGeometry args={[1.6, 0.7, 0.05]} />
        <meshStandardMaterial
          color={highlight === "window" ? "#67e8f9" : "#0c4a6e"}
          metalness={0.5}
          roughness={0.1}
          transparent
          opacity={0.7}
        />
      </mesh>

      {/* 后挡风玻璃 */}
      <mesh
        position={[0, 0.75, -1.5]}
        rotation={[Math.PI * -0.12, 0, 0]}
        onClick={() => onPartClick("window")}
        castShadow
      >
        <boxGeometry args={[1.6, 0.6, 0.05]} />
        <meshStandardMaterial
          color={highlight === "window" ? "#67e8f9" : "#0c4a6e"}
          metalness={0.5}
          roughness={0.1}
          transparent
          opacity={0.7}
        />
      </mesh>

      {/* 左侧车窗 */}
      <mesh
        position={[-0.95, 0.75, -0.2]}
        onClick={() => onPartClick("window")}
        castShadow
      >
        <boxGeometry args={[0.05, 0.5, 1.8]} />
        <meshStandardMaterial
          color={highlight === "window" ? "#67e8f9" : "#0c4a6e"}
          metalness={0.5}
          roughness={0.1}
          transparent
          opacity={0.6}
        />
      </mesh>

      {/* 右侧车窗 */}
      <mesh
        position={[0.95, 0.75, -0.2]}
        onClick={() => onPartClick("window")}
        castShadow
      >
        <boxGeometry args={[0.05, 0.5, 1.8]} />
        <meshStandardMaterial
          color={highlight === "window" ? "#67e8f9" : "#0c4a6e"}
          metalness={0.5}
          roughness={0.1}
          transparent
          opacity={0.6}
        />
      </mesh>

      {/* 前轮 */}
      <mesh position={[-1.1, 0, 1.3]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.4, 0.4, 0.3, 16]} />
        <meshStandardMaterial color="#1a1a1a" metalness={0.3} roughness={0.7} />
      </mesh>
      <mesh position={[1.1, 0, 1.3]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.4, 0.4, 0.3, 16]} />
        <meshStandardMaterial color="#1a1a1a" metalness={0.3} roughness={0.7} />
      </mesh>

      {/* 后轮 */}
      <mesh position={[-1.1, 0, -1.3]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.4, 0.4, 0.3, 16]} />
        <meshStandardMaterial color="#1a1a1a" metalness={0.3} roughness={0.7} />
      </mesh>
      <mesh position={[1.1, 0, -1.3]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.4, 0.4, 0.3, 16]} />
        <meshStandardMaterial color="#1a1a1a" metalness={0.3} roughness={0.7} />
      </mesh>

      {/* 前灯 */}
      <mesh position={[-0.7, 0.3, 2]} castShadow>
        <boxGeometry args={[0.4, 0.2, 0.05]} />
        <meshStandardMaterial
          color="#e0f2fe"
          emissive="#7dd3fc"
          emissiveIntensity={0.5}
        />
      </mesh>
      <mesh position={[0.7, 0.3, 2]} castShadow>
        <boxGeometry args={[0.4, 0.2, 0.05]} />
        <meshStandardMaterial
          color="#e0f2fe"
          emissive="#7dd3fc"
          emissiveIntensity={0.5}
        />
      </mesh>

      {/* 尾灯 */}
      <mesh position={[-0.7, 0.3, -2]} castShadow>
        <boxGeometry args={[0.4, 0.2, 0.05]} />
        <meshStandardMaterial
          color="#7f1d1d"
          emissive="#ef4444"
          emissiveIntensity={0.3}
        />
      </mesh>
      <mesh position={[0.7, 0.3, -2]} castShadow>
        <boxGeometry args={[0.4, 0.2, 0.05]} />
        <meshStandardMaterial
          color="#7f1d1d"
          emissive="#ef4444"
          emissiveIntensity={0.3}
        />
      </mesh>
    </group>
  );
}

export function Vehicle3DModel({
  onPartClick,
  className,
}: {
  onPartClick?: (part: string) => void;
  className?: string;
}) {
  const [highlight, setHighlight] = useState<string | null>(null);

  const handlePartClick = (part: string) => {
    setHighlight(part);
    setTimeout(() => setHighlight(null), 2000);
    onPartClick?.(part);
  };

  return (
    <div className={className} style={{ width: "100%", height: "300px" }}>
      <Canvas shadows camera={{ position: [4, 3, 5], fov: 40 }}>
        <ambientLight intensity={0.5} />
        <spotLight
          position={[5, 8, 5]}
          angle={0.3}
          penumbra={1}
          intensity={1.5}
          castShadow
        />
        <CarBody highlight={highlight} onPartClick={handlePartClick} />
        <ContactShadows
          position={[0, -0.5, 0]}
          opacity={0.4}
          scale={10}
          blur={2}
          far={4}
        />
        {/* 环境光: 用多方向点光源模拟 HDR 环境光照，避免 CDN 依赖 */}
        <pointLight position={[5, 5, 5]} intensity={0.6} color="#4fc3f7" />
        <pointLight position={[-5, 3, -5]} intensity={0.4} color="#7c4dff" />
        <pointLight position={[0, -3, 0]} intensity={0.2} color="#ff6f00" />
        <OrbitControls
          enablePan={false}
          minDistance={5}
          maxDistance={12}
          minPolarAngle={Math.PI / 4}
          maxPolarAngle={Math.PI / 2}
          autoRotate
          autoRotateSpeed={0.5}
        />
      </Canvas>
    </div>
  );
}
