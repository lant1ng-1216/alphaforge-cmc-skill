import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

const COLORS = {
  bg: "#0a0b10",
  bgGlow: "#14182a",
  text: "#e7e9ee",
  textDim: "#8a8f9e",
  accent: "#4fc3f7",
  accent2: "#4caf50",
  border: "#232838",
};

export const Intro = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logoScale = spring({ frame, fps, config: { damping: 200, stiffness: 120 }, durationInFrames: 24 });
  const logoOpacity = interpolate(frame, [0, 18], [0, 1], { extrapolateRight: "clamp" });

  const nameOpacity = interpolate(frame, [16, 34], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const nameY = interpolate(frame, [16, 34], [14, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const taglineOpacity = interpolate(frame, [46, 70], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const taglineY = interpolate(frame, [46, 70], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const tagOpacity = interpolate(frame, [92, 112], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const fadeOut = interpolate(frame, [205, 240], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        backgroundImage: `radial-gradient(ellipse 80% 60% at 50% 35%, ${COLORS.bgGlow} 0%, ${COLORS.bg} 65%)`,
        opacity: fadeOut,
      }}
    >
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 28,
              opacity: logoOpacity,
              transform: `scale(${0.85 + logoScale * 0.15})`,
            }}
          >
            <Img src={staticFile("logo.png")} style={{ width: 130, height: "auto" }} />
            <div
              style={{
                fontFamily: "Arial, Helvetica, sans-serif",
                fontWeight: 800,
                fontSize: 96,
                color: COLORS.text,
                letterSpacing: -2,
                opacity: nameOpacity,
                transform: `translateY(${nameY}px)`,
              }}
            >
              AlphaForge
            </div>
          </div>

          <div
            style={{
              marginTop: 36,
              fontFamily: "Arial, Helvetica, sans-serif",
              fontSize: 30,
              fontWeight: 500,
              color: COLORS.textDim,
              opacity: taglineOpacity,
              transform: `translateY(${taglineY}px)`,
              textAlign: "center",
              maxWidth: 980,
            }}
          >
            A Quantopian-style crypto strategy generation Skill,
            <br />
            powered by CoinMarketCap.
          </div>

          <div
            style={{
              marginTop: 44,
              padding: "10px 22px",
              borderRadius: 999,
              border: `1px solid ${COLORS.border}`,
              fontFamily: "SF Mono, Menlo, monospace",
              fontSize: 18,
              color: COLORS.accent,
              opacity: tagOpacity,
              letterSpacing: 0.5,
            }}
          >
            BNB Hack: AI Trading Agent Edition · Track 2 — Strategy Skills
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
