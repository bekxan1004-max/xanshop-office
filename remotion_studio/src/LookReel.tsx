import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export interface ReelItemProp {
  name: string;
  priceUzs: number;
  imageFile: string;
}

export interface LookReelProps {
  shopBrand: string;
  lookTitle: string;
  subtitleHook: string;
  totalPriceUzs: number;
  prepay50Uzs: number;
  themeVariant: "editorial_light" | "obsidian_gold";
  audioFile: string;
  items: ReelItemProp[];
}

const fmt = (n: number): string =>
  Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");

const HighlightTitle: React.FC<{
  text: string;
  isLight: boolean;
  frame: number;
  fps: number;
}> = ({ text, isLight, frame, fps }) => {
  const words = (text || "").trim().split(/\s+/);
  const highlightIdx = words.length > 2 ? words.length - 1 : 0;
  const lineProgress = spring({
    frame: Math.max(0, frame - 4),
    fps,
    config: { damping: 16, stiffness: 110 },
  });

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        gap: "12px",
        fontSize: words.length > 5 ? 48 : 56,
        fontWeight: 800,
        lineHeight: 1.15,
        textAlign: "center",
        color: isLight ? "#1B1917" : "#F8F6F2",
        fontFamily: "Inter, Segoe UI, Arial, sans-serif",
      }}
    >
      {words.map((w, idx) => {
        const isHot = idx === highlightIdx;
        return (
          <span
            key={idx}
            style={{
              position: "relative",
              color: isHot ? (isLight ? "#B85337" : "#E2B857") : "inherit",
              fontStyle: isHot ? "italic" : "normal",
              fontFamily: isHot ? "Georgia, serif" : "inherit",
            }}
          >
            {w}
            {isHot && (
              <span
                style={{
                  position: "absolute",
                  left: 0,
                  bottom: -6,
                  height: 6,
                  width: `${Math.min(100, lineProgress * 100)}%`,
                  borderRadius: 4,
                  backgroundColor: isLight ? "#B85337" : "#E2B857",
                }}
              />
            )}
          </span>
        );
      })}
    </div>
  );
};

export const LookReel: React.FC<LookReelProps> = ({
  shopBrand,
  lookTitle,
  subtitleHook,
  totalPriceUzs,
  prepay50Uzs,
  themeVariant,
  audioFile,
  items,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const isLight = themeVariant !== "obsidian_gold";

  const framesPerItem = 48;
  const safeItems = items && items.length > 0 ? items : [{ name: "Kiyim", priceUzs: 400000, imageFile: "" }];
  const itemsTotalFrames = safeItems.length * framesPerItem;
  const isFinale = frame >= itemsTotalFrames;
  const activeIdx = Math.min(safeItems.length - 1, Math.floor(frame / framesPerItem));

  const bgGradient = isLight
    ? "radial-gradient(circle at 50% 28%, #FFFDF9 0%, #F3ECE0 58%, #E6DDD0 100%)"
    : "radial-gradient(circle at 50% 28%, #1C2029 0%, #101218 65%, #090A0D 100%)";

  const cardBg = isLight ? "#FFFFFF" : "#171A22";
  const borderCol = isLight ? "rgba(184, 83, 55, 0.25)" : "rgba(226, 184, 87, 0.40)";
  const accentCol = isLight ? "#B85337" : "#E2B857";
  const mutedText = isLight ? "#5E5850" : "#B8B5AE";

  return (
    <AbsoluteFill
      style={{
        background: bgGradient,
        fontFamily: "Inter, Segoe UI, Arial, sans-serif",
        padding: "56px 54px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      {/* Subtle animated decorative bokeh circles (editorial paper vibe) */}
      <div
        style={{
          position: "absolute",
          top: -80 + Math.sin(frame / 25) * 18,
          right: -90,
          width: 420,
          height: 420,
          borderRadius: "50%",
          border: `3px solid ${isLight ? "rgba(184,83,55,0.08)" : "rgba(226,184,87,0.07)"}`,
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: 140 + Math.cos(frame / 30) * 16,
          left: -120,
          width: 360,
          height: 360,
          borderRadius: "50%",
          border: `3px solid ${isLight ? "rgba(27,25,23,0.06)" : "rgba(255,255,255,0.05)"}`,
          pointerEvents: "none",
        }}
      />

      {/* Audio track with smooth fade-in and fade-out */}
      {audioFile ? (
        <Audio
          src={staticFile(audioFile)}
          volume={(f) => {
            const fadeIn = interpolate(f, [0, 15], [0.1, 0.9], { extrapolateRight: "clamp" });
            const fadeOut = interpolate(
              f,
              [Math.max(16, durationInFrames - 22), durationInFrames],
              [0.9, 0.05],
              { extrapolateLeft: "clamp" }
            );
            return Math.min(fadeIn, fadeOut);
          }}
        />
      ) : null}

      {/* Top Bar: Stories progress indicators + Brand Pill + Headline */}
      <div style={{ display: "flex", flexDirection: "column", gap: 22, zIndex: 2 }}>
        <div style={{ display: "flex", gap: 10 }}>
          {[...safeItems, { name: "Final" }].map((_, idx) => {
            const segStart = idx * framesPerItem;
            const segLen = idx === safeItems.length ? durationInFrames - itemsTotalFrames : framesPerItem;
            const pct = interpolate(frame, [segStart, segStart + segLen], [0, 100], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <div
                key={idx}
                style={{
                  flex: 1,
                  height: 6,
                  borderRadius: 4,
                  backgroundColor: isLight ? "rgba(27,25,23,0.12)" : "rgba(255,255,255,0.15)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${pct}%`,
                    height: "100%",
                    backgroundColor: accentCol,
                  }}
                />
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div
            style={{
              backgroundColor: accentCol,
              color: "#FFFFFF",
              fontWeight: 800,
              fontSize: 24,
              padding: "10px 24px",
              borderRadius: 999,
              letterSpacing: 1.5,
            }}
          >
            {shopBrand} · AVIA 5–10 KUN
          </div>
          <div
            style={{
              color: isLight ? "#1B1917" : "#F5F2EB",
              fontSize: 26,
              fontWeight: 700,
              opacity: 0.85,
            }}
          >
            {isFinale ? "TO'LIQ LOOK" : `${activeIdx + 1} / ${safeItems.length}`}
          </div>
        </div>

        <HighlightTitle text={lookTitle} isLight={isLight} frame={frame} fps={fps} />

        <div
          style={{
            textAlign: "center",
            color: mutedText,
            fontSize: 28,
            fontWeight: 500,
          }}
        >
          {subtitleHook}
        </div>
      </div>

      {/* Middle Stage: Animated Product Scenes + Finale Collage */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          margin: "20px 0",
        }}
      >
        {!isFinale ? (
          safeItems.map((it, idx) => {
            if (idx !== activeIdx) return null;
            const localF = frame - idx * framesPerItem;
            const enter = spring({
              frame: localF,
              fps,
              config: { damping: 14, stiffness: 130 },
            });
            const breathe = interpolate(localF, [0, framesPerItem], [1.0, 1.04]);
            const scale = interpolate(enter, [0, 1], [0.88, 1.0]) * breathe;
            const translateY = interpolate(enter, [0, 1], [55, 0]);
            const opacity = interpolate(localF, [0, 7, framesPerItem - 5, framesPerItem], [0, 1, 1, 0.25]);

            return (
              <Sequence key={idx} from={idx * framesPerItem} durationInFrames={framesPerItem} layout="none">
                <div
                  style={{
                    width: "100%",
                    height: 980,
                    backgroundColor: cardBg,
                    borderRadius: 44,
                    border: `3px solid ${borderCol}`,
                    boxShadow: isLight
                      ? "0 28px 65px rgba(27,25,23,0.12)"
                      : "0 28px 65px rgba(0,0,0,0.55)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    padding: 36,
                    transform: `translateY(${translateY}px) scale(${scale})`,
                    opacity,
                  }}
                >
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      backgroundColor: isLight ? "#FBF8F3" : "#FAF6EE",
                      borderRadius: 28,
                      overflow: "hidden",
                      padding: 20,
                    }}
                  >
                    {it.imageFile ? (
                      <Img
                        src={staticFile(it.imageFile)}
                        style={{
                          maxWidth: "100%",
                          maxHeight: "100%",
                          objectFit: "contain",
                        }}
                      />
                    ) : (
                      <div style={{ fontSize: 42, color: "#888" }}>{it.name}</div>
                    )}
                  </div>

                  <div
                    style={{
                      marginTop: 28,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 16,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 38,
                        fontWeight: 800,
                        color: isLight ? "#1B1917" : "#FFFFFF",
                        flex: 1,
                      }}
                    >
                      {it.name}
                    </div>
                    <div
                      style={{
                        backgroundColor: accentCol,
                        color: "#FFFFFF",
                        fontSize: 30,
                        fontWeight: 800,
                        padding: "12px 24px",
                        borderRadius: 20,
                        whiteSpace: "nowrap",
                      }}
                    >
                      ~{fmt(it.priceUzs)} so'm
                    </div>
                  </div>
                </div>
              </Sequence>
            );
          })
        ) : (
          /* Finale Grid Showcase + CTA */
          <div
            style={{
              width: "100%",
              height: "100%",
              minHeight: 0,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              gap: 20,
              transform: `scale(${spring({
                frame: frame - itemsTotalFrames,
                fps,
                config: { damping: 14, stiffness: 120 },
              })})`,
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: safeItems.length === 1 ? "1fr" : "1fr 1fr",
                gridTemplateRows:
                  safeItems.length > 2 ? "minmax(0, 1fr) minmax(0, 1fr)" : "minmax(0, 1fr)",
                gap: 18,
                flex: 1,
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              {safeItems.slice(0, 4).map((it, idx) => (
                <div
                  key={idx}
                  style={{
                    minHeight: 0,
                    overflow: "hidden",
                    backgroundColor: cardBg,
                    borderRadius: 28,
                    border: `2px solid ${borderCol}`,
                    padding: 14,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      flex: 1,
                      minHeight: 0,
                      overflow: "hidden",
                      backgroundColor: "#FAF6EE",
                      borderRadius: 18,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 8,
                    }}
                  >
                    {it.imageFile && (
                      <Img
                        src={staticFile(it.imageFile)}
                        style={{
                          width: "100%",
                          height: "100%",
                          maxWidth: "100%",
                          maxHeight: "100%",
                          objectFit: "contain",
                        }}
                      />
                    )}
                  </div>
                  <div
                    style={{
                      flexShrink: 0,
                      fontSize: 22,
                      fontWeight: 700,
                      color: isLight ? "#1B1917" : "#F8F6F2",
                      textAlign: "center",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {it.name}
                  </div>
                </div>
              ))}
            </div>

            <div
              style={{
                flexShrink: 0,
                backgroundColor: accentCol,
                color: "#FFFFFF",
                borderRadius: 22,
                padding: "18px 26px",
                textAlign: "center",
                fontSize: 30,
                fontWeight: 800,
              }}
            >
              💬 KOMMENTGA «+» YOZING — BUYURTMA LINKI DIRECTGA!
            </div>
          </div>
        )}
      </div>

      {/* Bottom Price Banner */}
      <div
        style={{
          backgroundColor: isLight ? "#1B1917" : "#181B24",
          borderRadius: 34,
          border: `3px solid ${accentCol}`,
          padding: "30px 36px",
          color: "#FFFFFF",
          display: "flex",
          flexDirection: "column",
          gap: 10,
          zIndex: 2,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: 42, fontWeight: 900, color: "#E2B857" }}>
            Hozirgi narx (50%): {fmt(prepay50Uzs)} so'm
          </div>
        </div>
        <div style={{ fontSize: 28, fontWeight: 700, color: "#5CE1A6" }}>
          + kargo (qolgan 50% + kargo kiyim Toshkentga kelganda)
        </div>
        <div style={{ fontSize: 24, color: "#C8C5BE" }}>
          To'liq narxi: {fmt(totalPriceUzs)} so'm · Kiyimni Toshkentda ko'rib olganda to'laysiz!
        </div>
      </div>
    </AbsoluteFill>
  );
};
