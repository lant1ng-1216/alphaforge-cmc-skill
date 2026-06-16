import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";

const COLORS = {
  bg: "#0a0b10",
  bgGlow: "#14182a",
  panel: "#12141c",
  panel2: "#161924",
  border: "#232838",
  text: "#e7e9ee",
  textDim: "#8a8f9e",
  textFaint: "#565b6c",
  accent: "#4fc3f7",
  accent2: "#4caf50",
};

const Row = ({ frame, appearAt, label, value, color }) => {
  const opacity = interpolate(frame, [appearAt, appearAt + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const x = interpolate(frame, [appearAt, appearAt + 14], [-16, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 14,
        opacity,
        transform: `translateX(${x}px)`,
        fontFamily: "SF Mono, Menlo, monospace",
        fontSize: 24,
      }}
    >
      <span style={{ color: COLORS.textDim, minWidth: 150 }}>{label}</span>
      <span style={{ color: color || COLORS.text, fontWeight: 700 }}>{value}</span>
    </div>
  );
};

export const Outro = () => {
  const frame = useCurrentFrame();

  const headerOpacity = interpolate(frame, [0, 18], [0, 1], { extrapolateRight: "clamp" });
  const cardOpacity = interpolate(frame, [10, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const disclaimerOpacity = interpolate(frame, [150, 175], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frame, [205, 240], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        backgroundImage: `radial-gradient(ellipse 80% 60% at 50% 30%, ${COLORS.bgGlow} 0%, ${COLORS.bg} 65%)`,
        opacity: fadeOut,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            opacity: headerOpacity,
          }}
        >
          <Img src={staticFile("logo.png")} style={{ width: 56, height: "auto" }} />
          <span
            style={{
              fontFamily: "Arial, Helvetica, sans-serif",
              fontWeight: 800,
              fontSize: 48,
              color: COLORS.text,
              letterSpacing: -1,
            }}
          >
            AlphaForge
          </span>
        </div>

        <div
          style={{
            opacity: cardOpacity,
            background: COLORS.panel,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 16,
            padding: "32px 48px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <Row frame={frame} appearAt={30} label="Live demo" value="alphaforge-cmc-skill.vercel.app" color={COLORS.accent} />
          <Row frame={frame} appearAt={50} label="GitHub" value="github.com/lant1ng-1216/alphaforge-cmc-skill" color={COLORS.accent2} />
          <Row frame={frame} appearAt={70} label="Built for" value="BNB Hack — Track 2: Strategy Skills" />
        </div>

        <div
          style={{
            opacity: disclaimerOpacity,
            fontFamily: "Arial, Helvetica, sans-serif",
            fontSize: 16,
            color: COLORS.textFaint,
            maxWidth: 760,
            textAlign: "center",
            lineHeight: 1.5,
          }}
        >
          Not financial advice. AlphaForge generates research-grade strategy specifications
          for educational and analytical purposes only — it does not execute trades or manage funds.
        </div>
      </div>
    </AbsoluteFill>
  );
};
