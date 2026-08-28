import { useState, useEffect, useRef } from 'react';

interface PupilProps {
  size?: number;
  maxDistance?: number;
  pupilColor?: string;
  forceLookX?: number;
  forceLookY?: number;
}

export const Pupil = ({
  size = 12,
  maxDistance = 5,
  pupilColor = 'black',
  forceLookX,
  forceLookY,
}: PupilProps) => {
  const [mouseX, setMouseX] = useState<number>(0);
  const [mouseY, setMouseY] = useState<number>(0);
  const pupilRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMouseX(e.clientX);
      setMouseY(e.clientY);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const calculatePupilPosition = () => {
    if (!pupilRef.current) return { x: 0, y: 0 };
    if (forceLookX !== undefined && forceLookY !== undefined) {
      return { x: forceLookX, y: forceLookY };
    }
    const pupil = pupilRef.current.getBoundingClientRect();
    const pupilCenterX = pupil.left + pupil.width / 2;
    const pupilCenterY = pupil.top + pupil.height / 2;
    const deltaX = mouseX - pupilCenterX;
    const deltaY = mouseY - pupilCenterY;
    const distance = Math.min(Math.sqrt(deltaX ** 2 + deltaY ** 2), maxDistance);
    const angle = Math.atan2(deltaY, deltaX);
    return { x: Math.cos(angle) * distance, y: Math.sin(angle) * distance };
  };

  const pupilPosition = calculatePupilPosition();

  return (
    <div
      ref={pupilRef}
      className="rounded-full"
      style={{
        width: `${size}px`,
        height: `${size}px`,
        backgroundColor: pupilColor,
        transform: `translate(${pupilPosition.x}px, ${pupilPosition.y}px)`,
        transition: 'transform 0.1s ease-out',
      }}
    />
  );
};

interface EyeBallProps {
  size?: number;
  pupilSize?: number;
  maxDistance?: number;
  eyeColor?: string;
  pupilColor?: string;
  isBlinking?: boolean;
  forceLookX?: number;
  forceLookY?: number;
}

export const EyeBall = ({
  size = 48,
  pupilSize = 16,
  maxDistance = 10,
  eyeColor = 'white',
  pupilColor = 'black',
  isBlinking = false,
  forceLookX,
  forceLookY,
}: EyeBallProps) => {
  const [mouseX, setMouseX] = useState<number>(0);
  const [mouseY, setMouseY] = useState<number>(0);
  const eyeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMouseX(e.clientX);
      setMouseY(e.clientY);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const calculatePupilPosition = () => {
    if (!eyeRef.current) return { x: 0, y: 0 };
    if (forceLookX !== undefined && forceLookY !== undefined) {
      return { x: forceLookX, y: forceLookY };
    }
    const eye = eyeRef.current.getBoundingClientRect();
    const eyeCenterX = eye.left + eye.width / 2;
    const eyeCenterY = eye.top + eye.height / 2;
    const deltaX = mouseX - eyeCenterX;
    const deltaY = mouseY - eyeCenterY;
    const distance = Math.min(Math.sqrt(deltaX ** 2 + deltaY ** 2), maxDistance);
    const angle = Math.atan2(deltaY, deltaX);
    return { x: Math.cos(angle) * distance, y: Math.sin(angle) * distance };
  };

  const pupilPosition = calculatePupilPosition();

  return (
    <div
      ref={eyeRef}
      className="rounded-full flex items-center justify-center transition-all duration-150"
      style={{
        width: `${size}px`,
        height: isBlinking ? '2px' : `${size}px`,
        backgroundColor: eyeColor,
        overflow: 'hidden',
      }}
    >
      {!isBlinking && (
        <div
          className="rounded-full"
          style={{
            width: `${pupilSize}px`,
            height: `${pupilSize}px`,
            backgroundColor: pupilColor,
            transform: `translate(${pupilPosition.x}px, ${pupilPosition.y}px)`,
            transition: 'transform 0.1s ease-out',
          }}
        />
      )}
    </div>
  );
};

interface AnimatedCharactersProps {
  isTyping?: boolean;
  showPassword?: boolean;
  passwordLength?: number;
  isPasswordFieldFocused?: boolean;
}

// 新角色设计 - 完全原创的几何形状角色
export function AnimatedCharacters({
  isTyping = false,
  showPassword = false,
  passwordLength = 0,
  isPasswordFieldFocused = false,
}: AnimatedCharactersProps) {
  const [mouseX, setMouseX] = useState<number>(0);
  const [mouseY, setMouseY] = useState<number>(0);
  const [isBlinking1, setIsBlinking1] = useState(false);
  const [isBlinking2, setIsBlinking2] = useState(false);
  const [isBlinking3, setIsBlinking3] = useState(false);
  const [isBlinking4, setIsBlinking4] = useState(false);
  const [isLookingAtEachOther, setIsLookingAtEachOther] = useState(false);
  const [isPeeking, setIsPeeking] = useState(false);
  const char1Ref = useRef<HTMLDivElement>(null);
  const char2Ref = useRef<HTMLDivElement>(null);
  const char3Ref = useRef<HTMLDivElement>(null);
  const char4Ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMouseX(e.clientX);
      setMouseY(e.clientY);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // 眨眼动画
  useEffect(() => {
    const scheduleBlink = (setter: (v: boolean) => void) => {
      const blink = () => {
        const timeout = setTimeout(() => {
          setter(true);
          setTimeout(() => setter(false), 150);
          blink();
        }, Math.random() * 4000 + 3000);
        return timeout;
      };
      return blink();
    };
    const t1 = scheduleBlink(setIsBlinking1);
    const t2 = scheduleBlink(setIsBlinking2);
    const t3 = scheduleBlink(setIsBlinking3);
    const t4 = scheduleBlink(setIsBlinking4);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); clearTimeout(t4); };
  }, []);

  // 互相看动画
  useEffect(() => {
    if (isTyping) {
      setIsLookingAtEachOther(true);
      const timer = setTimeout(() => setIsLookingAtEachOther(false), 800);
      return () => clearTimeout(timer);
    }
  }, [isTyping]);

  // 偷看动画
  useEffect(() => {
    if (passwordLength > 0 && (showPassword || isPasswordFieldFocused)) {
      const peek = () => {
        const timeout = setTimeout(() => {
          setIsPeeking(true);
          setTimeout(() => setIsPeeking(false), 800);
        }, Math.random() * 2000 + 1000);
        return timeout;
      };
      const first = peek();
      return () => clearTimeout(first);
    }
  }, [passwordLength, showPassword, isPasswordFieldFocused, isPeeking]);

  const calculatePosition = (ref: React.RefObject<HTMLDivElement | null>) => {
    if (!ref.current) return { faceX: 0, faceY: 0, bodySkew: 0 };
    const rect = ref.current.getBoundingClientRect();
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

  const pos1 = calculatePosition(char1Ref);
  const pos2 = calculatePosition(char2Ref);
  const pos3 = calculatePosition(char3Ref);
  const pos4 = calculatePosition(char4Ref);

  const shouldPeek = passwordLength > 0 && (showPassword || isPasswordFieldFocused);

  return (
    <div className="relative" style={{ width: '550px', height: '450px' }}>
      {/* 角色1: 大黄色圆球 - 包裹其他角色的背景 */}
      <div
        ref={char1Ref}
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '10px',
          width: '520px',
          height: `${isTyping || (passwordLength > 0 && !showPassword) ? '480px' : '460px'}`,
          backgroundColor: '#F5D76E',
          borderRadius: '260px 260px 40px 40px',
          zIndex: 0,
          transform: shouldPeek
            ? 'skewX(0deg)'
            : isTyping || (passwordLength > 0 && !showPassword)
              ? `skewX(${(pos1.bodySkew || 0) - 4}deg)`
              : `skewX(${pos1.bodySkew || 0}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        {/* 眼睛 - 在圆球顶部 */}
        <div
          className="absolute flex gap-16 transition-all duration-700"
          style={{
            left: shouldPeek ? '180px' : isLookingAtEachOther ? '220px' : `${210 + pos1.faceX}px`,
            top: shouldPeek ? '80px' : isLookingAtEachOther ? '100px' : `${90 + pos1.faceY}px`,
          }}
        >
          <EyeBall size={24} pupilSize={10} maxDistance={7} eyeColor="white" pupilColor="#2D3436" isBlinking={isBlinking1}
            forceLookX={shouldPeek ? (isPeeking ? 6 : -6) : isLookingAtEachOther ? 5 : undefined}
            forceLookY={shouldPeek ? (isPeeking ? 7 : -6) : isLookingAtEachOther ? 6 : undefined} />
          <EyeBall size={24} pupilSize={10} maxDistance={7} eyeColor="white" pupilColor="#2D3436" isBlinking={isBlinking1}
            forceLookX={shouldPeek ? (isPeeking ? 6 : -6) : isLookingAtEachOther ? 5 : undefined}
            forceLookY={shouldPeek ? (isPeeking ? 7 : -6) : isLookingAtEachOther ? 6 : undefined} />
        </div>

      </div>

      {/* 左手 - 从左侧抱住角色3 */}
      <div
        className="absolute transition-all duration-700"
        style={{
          left: '40px',
          bottom: '60px',
          width: '90px',
          height: '50px',
          backgroundColor: '#F5D76E',
          borderRadius: '25px 15px 15px 25px',
          transform: `rotate(-8deg)`,
          zIndex: 7,
        }}
      />

      {/* 右手 - 从右侧抱住角色4 */}
      <div
        className="absolute transition-all duration-700"
        style={{
          right: '40px',
          bottom: '80px',
          width: '90px',
          height: '50px',
          backgroundColor: '#F5D76E',
          borderRadius: '15px 25px 25px 15px',
          transform: `rotate(8deg)`,
          zIndex: 7,
        }}
      />

      {/* 角色2: 矮胖椭圆 - 珊瑚橙 (中间) */}
      <div
        ref={char2Ref}
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '210px',
          width: '140px',
          height: '180px',
          backgroundColor: '#FF8C6B',
          borderRadius: '60px 60px 15px 15px',
          zIndex: 5,
          transform: shouldPeek
            ? 'skewX(0deg)'
            : isLookingAtEachOther
              ? `skewX(${(pos2.bodySkew || 0) * 1.3 + 6}deg) translateX(10px)`
              : isTyping || (passwordLength > 0 && !showPassword)
                ? `skewX(${(pos2.bodySkew || 0) * 1.3}deg)`
                : `skewX(${pos2.bodySkew || 0}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        {/* 眼睛 */}
        <div
          className="absolute flex gap-5 transition-all duration-700"
          style={{
            left: shouldPeek ? '25px' : isLookingAtEachOther ? '40px' : `${30 + pos2.faceX}px`,
            top: shouldPeek ? '50px' : isLookingAtEachOther ? '40px' : `${48 + pos2.faceY}px`,
          }}
        >
          <EyeBall size={13} pupilSize={5} maxDistance={4} eyeColor="white" pupilColor="#2D3436" isBlinking={isBlinking2}
            forceLookX={shouldPeek ? -4 : isLookingAtEachOther ? 0 : undefined}
            forceLookY={shouldPeek ? -3 : isLookingAtEachOther ? -3 : undefined} />
          <EyeBall size={13} pupilSize={5} maxDistance={4} eyeColor="white" pupilColor="#2D3436" isBlinking={isBlinking2}
            forceLookX={shouldPeek ? -4 : isLookingAtEachOther ? 0 : undefined}
            forceLookY={shouldPeek ? -3 : isLookingAtEachOther ? -3 : undefined} />
        </div>
      </div>

      {/* 角色3: 方形小人 - 天空蓝 (最左侧) */}
      <div
        ref={char3Ref}
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '80px',
          width: '130px',
          height: '240px',
          backgroundColor: '#5B9BD5',
          borderRadius: '15px 15px 8px 8px',
          zIndex: 4,
          transform: shouldPeek
            ? 'skewX(0deg)'
            : `skewX(${pos3.bodySkew || 0}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        {/* 眼睛 */}
        <div
          className="absolute flex gap-5 transition-all duration-200"
          style={{
            left: shouldPeek ? '25px' : `${32 + (pos3.faceX || 0)}px`,
            top: shouldPeek ? '60px' : `${60 + (pos3.faceY || 0)}px`,
          }}
        >
          <Pupil size={11} maxDistance={4} pupilColor="#2D3436"
            forceLookX={shouldPeek ? -4 : undefined} forceLookY={shouldPeek ? -3 : undefined} />
          <Pupil size={11} maxDistance={4} pupilColor="#2D3436"
            forceLookX={shouldPeek ? -4 : undefined} forceLookY={shouldPeek ? -3 : undefined} />
        </div>
      </div>

      {/* 角色4: 高瘦长条 - 薰衣草紫 (最右侧) */}
      <div
        ref={char4Ref}
        className="absolute bottom-0 transition-all duration-700 ease-in-out"
        style={{
          left: '350px',
          width: '100px',
          height: '280px',
          backgroundColor: '#9B8EC4',
          borderRadius: '50px 50px 12px 12px',
          zIndex: 5,
          transform: shouldPeek
            ? 'skewX(0deg)'
            : `skewX(${pos4.bodySkew || 0}deg)`,
          transformOrigin: 'bottom center',
        }}
      >
        {/* 眼睛 */}
        <div
          className="absolute flex gap-4 transition-all duration-200"
          style={{
            left: shouldPeek ? '18px' : `${25 + (pos4.faceX || 0)}px`,
            top: shouldPeek ? '55px' : `${60 + (pos4.faceY || 0)}px`,
          }}
        >
          <Pupil size={9} maxDistance={3} pupilColor="#2D3436"
            forceLookX={shouldPeek ? -3 : undefined} forceLookY={shouldPeek ? -3 : undefined} />
          <Pupil size={9} maxDistance={3} pupilColor="#2D3436"
            forceLookX={shouldPeek ? -3 : undefined} forceLookY={shouldPeek ? -3 : undefined} />
        </div>
        {/* 嘴巴 */}
        <div
          className="absolute w-9 h-[2px] bg-[#2D3436]/40 rounded-full transition-all duration-200"
          style={{
            left: shouldPeek ? '12px' : `${18 + (pos4.faceX || 0)}px`,
            top: shouldPeek ? '82px' : `${82 + (pos4.faceY || 0)}px`,
          }}
        />
      </div>
    </div>
  );
}
