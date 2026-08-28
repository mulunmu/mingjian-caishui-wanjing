import { useState, useEffect, useRef } from 'react';
import { EyeBall } from './AnimatedCharacters';

type AssistantState = 'idle' | 'typing' | 'answering';

interface ResearchAssistantCharacterProps {
  state: AssistantState;
  className?: string;
  variant?: 'main' | 'secondary';
}

export function ResearchAssistantCharacter({
  state = 'idle',
  className = '',
  variant = 'main',
}: ResearchAssistantCharacterProps) {
  const [mouseX, setMouseX] = useState<number>(0);
  const [mouseY, setMouseY] = useState<number>(0);
  const [isBlinking, setIsBlinking] = useState(false);
  const [bounceOffset, setBounceOffset] = useState(0);
  const [mouthPhase, setMouthPhase] = useState(0);
  const characterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMouseX(e.clientX);
      setMouseY(e.clientY);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // 眨眼
  useEffect(() => {
    const blink = () => {
      const timeout = setTimeout(() => {
        setIsBlinking(true);
        setTimeout(() => setIsBlinking(false), 150);
        blink();
      }, Math.random() * 4000 + 3000);
      return timeout;
    };
    const t = blink();
    return () => clearTimeout(t);
  }, []);

  // 弹跳
  useEffect(() => {
    if (state === 'typing') {
      const i = setInterval(() => setBounceOffset(p => p === 0 ? -8 : 0), 300);
      return () => clearInterval(i);
    } else if (state === 'answering') {
      const i = setInterval(() => setBounceOffset(p => p === 0 ? -5 : p === -5 ? -10 : 0), 400);
      return () => clearInterval(i);
    } else {
      setBounceOffset(0);
    }
  }, [state]);

  // 嘴巴
  useEffect(() => {
    if (state === 'answering') {
      const i = setInterval(() => setMouthPhase(p => (p + 1) % 4), 200);
      return () => clearInterval(i);
    } else if (state === 'typing') {
      const i = setInterval(() => setMouthPhase(p => (p + 1) % 3), 250);
      return () => clearInterval(i);
    } else {
      setMouthPhase(0);
    }
  }, [state]);

  const calculatePosition = () => {
    if (!characterRef.current) return { faceX: 0, faceY: 0, bodySkew: 0 };
    const rect = characterRef.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 3;
    const deltaX = mouseX - centerX;
    const deltaY = mouseY - centerY;
    return {
      faceX: Math.max(-15, Math.min(15, deltaX / 20)),
      faceY: Math.max(-10, Math.min(10, deltaY / 30)),
      bodySkew: Math.max(-6, Math.min(6, -deltaX / 120)),
    };
  };

  const pos = calculatePosition();

  // 主角色: 薄荷绿方形, 副角色: 珊瑚橙椭圆
  const mainColor = variant === 'main' ? '#6BC5A0' : '#FF8C6B';
  const darkColor = variant === 'main' ? '#5AA88A' : '#E87A5C';
  const borderRadius = variant === 'main' ? '15px 15px 8px 8px' : '50px 50px 15px 15px';

  const getCharacterHeight = () => {
    switch (state) {
      case 'typing': return variant === 'main' ? '180px' : '170px';
      case 'answering': return variant === 'main' ? '200px' : '190px';
      default: return variant === 'main' ? '160px' : '150px';
    }
  };

  const getEyePosition = () => {
    const baseX = variant === 'main' ? 25 : 30;
    const baseY = variant === 'main' ? 45 : 50;
    switch (state) {
      case 'typing': return { left: `${baseX + pos.faceX}px`, top: `${baseY + pos.faceY}px` };
      case 'answering': return { left: `${baseX - 5 + pos.faceX}px`, top: `${baseY - 5 + pos.faceY}px` };
      default: return { left: `${baseX + pos.faceX}px`, top: `${baseY + pos.faceY}px` };
    }
  };

  const getForceLook = () => {
    if (state === 'typing') return { x: -3, y: 5 };
    if (state === 'answering') return { x: 3, y: -2 };
    return { x: undefined, y: undefined };
  };

  const forceLook = getForceLook();
  const eyePos = getEyePosition();

  const renderMouth = () => {
    const mouthLeft = variant === 'main' ? '30px' : '35px';
    const mouthTop = variant === 'main' ? '80px' : '85px';

    if (state === 'idle') {
      return (
        <div className="absolute w-8 h-[3px] bg-white/50 rounded-full transition-all duration-300"
          style={{ left: `${parseInt(mouthLeft) + pos.faceX}px`, top: `${parseInt(mouthTop) + pos.faceY}px` }} />
      );
    }
    if (state === 'typing') {
      const sizes = [{ w: 6, h: 8 }, { w: 8, h: 10 }, { w: 5, h: 7 }];
      const size = sizes[mouthPhase];
      return (
        <div className="absolute bg-white/60 rounded-full transition-all duration-150"
          style={{
            left: `${parseInt(mouthLeft) + 3 + pos.faceX}px`,
            top: `${parseInt(mouthTop) - 2 + pos.faceY}px`,
            width: `${size.w}px`, height: `${size.h}px`,
          }} />
      );
    }
    if (state === 'answering') {
      const shapes = [
        { w: 12, h: 6, r: '50%' }, { w: 10, h: 8, r: '40%' },
        { w: 14, h: 5, r: '50%' }, { w: 8, h: 7, r: '50%' },
      ];
      const shape = shapes[mouthPhase];
      return (
        <div className="absolute bg-white/60 transition-all duration-150"
          style={{
            left: `${parseInt(mouthLeft) + pos.faceX}px`,
            top: `${parseInt(mouthTop) - 4 + pos.faceY}px`,
            width: `${shape.w}px`, height: `${shape.h}px`, borderRadius: shape.r,
          }} />
      );
    }
    return null;
  };

  const width = variant === 'main' ? '100px' : '90px';

  return (
    <div ref={characterRef} className={`relative ${className}`} style={{ width: '120px', height: '220px' }}>
      {/* 身体 */}
      <div className="absolute bottom-0 transition-all duration-500 ease-in-out"
        style={{
          left: '10px', width, height: getCharacterHeight(),
          backgroundColor: mainColor, borderRadius,
          transform: `translateY(${bounceOffset}px) skewX(${state === 'idle' ? pos.bodySkew : 0}deg)`,
          transformOrigin: 'bottom center',
        }}>
        {/* 眼睛 */}
        <div className="absolute flex gap-4 transition-all duration-300 ease-out"
          style={{ left: eyePos.left, top: eyePos.top }}>
          <EyeBall size={18} pupilSize={7} maxDistance={6} eyeColor="white" pupilColor="#2D3436"
            isBlinking={isBlinking} forceLookX={forceLook.x} forceLookY={forceLook.y} />
          <EyeBall size={18} pupilSize={7} maxDistance={6} eyeColor="white" pupilColor="#2D3436"
            isBlinking={isBlinking} forceLookX={forceLook.x} forceLookY={forceLook.y} />
        </div>
        {/* 嘴巴 */}
        {renderMouth()}
      </div>

      {/* 手臂 */}
      <div className="absolute bottom-0 transition-all duration-500 ease-in-out"
        style={{
          left: state === 'typing' ? '0px' : '5px', width: '14px', height: '55px',
          backgroundColor: darkColor, borderRadius: '7px 0 0 0',
          transform: `translateY(${bounceOffset}px) rotate(${state === 'typing' ? -15 : 0}deg)`,
          transformOrigin: 'bottom right',
        }} />
      <div className="absolute bottom-0 transition-all duration-500 ease-in-out"
        style={{
          right: state === 'typing' ? '0px' : '5px', width: '14px', height: '55px',
          backgroundColor: darkColor, borderRadius: '0 7px 0 0',
          transform: `translateY(${bounceOffset}px) rotate(${state === 'typing' ? 15 : 0}deg)`,
          transformOrigin: 'bottom left',
        }} />
    </div>
  );
}
