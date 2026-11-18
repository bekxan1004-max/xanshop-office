import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
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

export const LookReel: React.FC<LookReelProps> = ({
  lookTitle,
  totalPriceUzs,
  prepay50Uzs,
  audioFile,
  items,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const safeItems =
    items && items.length > 0
      ? items
      : [{ name: "Kiyim", priceUzs: 400000, imageFile: "" }];

  // 1-qism (0s - 3.4s): @_tima_shop uslubidagi toza Flat-Lay Obzor ("RASMDA:" / "TRENDA YURGAN LOOKGA OBZOR")
  const flatlayFrames = Math.min(102, Math.floor(durationInFrames * 0.44));
  const isFlatlayPhase = frame < flatlayFrames;

  // Beat-drop qorayib o'tish effekti (TIMA_SHOP_UZ_2854 / 2766 4-sekunddagi kabi)
  const beatDropDim = interpolate(
    frame,
    [flatlayFrames - 9, flatlayFrames, flatlayFrames + 9],
    [0, 0.78, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const remFrames = Math.max(1, durationInFrames - flatlayFrames);
  const perItemFrames = Math.max(18, Math.floor(remFrames / safeItems.length));
  const activeIdx = Math.min(
    safeItems.length - 1,
    Math.max(0, Math.floor((frame - flatlayFrames) / perItemFrames))
  );
  const localItemFrame = Math.max(0, (frame - flatlayFrames) - activeIdx * perItemFrames);
  const activeItem = safeItems[activeIdx] || safeItems[0];

  const isClassic =
    (lookTitle || "").toLowerCase().includes("diplomat") ||
    (lookTitle || "").toLowerCase().includes("old money") ||
    (lookTitle || "").toLowerCase().includes("klassik");
  const topHookText = isClassic ? "RASMDA:" : "TRENDA YURGAN LOOKGA\nOBZOR";

  const flatlayZoom = interpolate(frame, [0, flatlayFrames], [0.97, 1.04], {
    extrapolateRight: "clamp",
  });

  const itemScale = spring({
    frame: localItemFrame,
    fps,
    config: { damping: 15, stiffness: 120 },
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(180deg, #343438 0%, #232326 100%)",
        fontFamily: "Inter, Segoe UI, Arial, sans-serif",
        padding: "72px 56px 64px 56px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      {/* Haqiqiy viral zvuk / musiqa */}
      {audioFile ? (
        <Audio
          src={staticFile(audioFile)}
          volume={(f) => {
            const fadeIn = interpolate(f, [0, 10], [0.25, 0.95], {
              extrapolateRight: "clamp",
            });
            const fadeOut = interpolate(
              f,
              [Math.max(12, durationInFrames - 18), durationInFrames],
              [0.95, 0.08],
              { extrapolateLeft: "clamp" }
            );
            return Math.min(fadeIn, fadeOut);
          }}
        />
      ) : null}

      {/* Yuqori minimalistik sarlavha ("RASMDA:" yoki "TRENDA YURGAN LOOKGA OBZOR") */}
      <div
        style={{
          paddingTop: isFlatlayPhase ? 90 : 30,
          textAlign: "center",
          zIndex: 2,
        }}
      >
        <div
          style={{
            color: "#FFFFFF",
            fontSize: isClassic ? 54 : 46,
            fontWeight: 900,
            letterSpacing: 1.2,
            lineHeight: 1.2,
            whiteSpace: "pre-line",
            textShadow: "0px 4px 16px rgba(0, 0, 0, 0.65)",
          }}
        >
          {isFlatlayPhase ? topHookText : lookTitle.toUpperCase()}
        </div>
      </div>

      {/* O'rta sahna: 1-qismda Barcha Kiyimlar Cutout Flat-Lay, 2-qismda Har bir kiyim yaqin planda */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          margin: "24px 0",
        }}
      >
        {isFlatlayPhase ? (
          <div
            style={{
              width: "100%",
              height: "100%",
              maxHeight: 1220,
              minHeight: 0,
              overflow: "hidden",
              display: "grid",
              gridTemplateColumns: safeItems.length === 1 ? "1fr" : "1fr 1fr",
              gridTemplateRows:
                safeItems.length > 2
                  ? "minmax(0, 1fr) minmax(0, 1fr)"
                  : "minmax(0, 1fr)",
              gap: 24,
              transform: `scale(${flatlayZoom})`,
            }}
          >
            {safeItems.slice(0, 4).map((it, idx) => (
              <div
                key={idx}
                style={{
                  minHeight: 0,
                  overflow: "hidden",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: 12,
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
                      filter: "drop-shadow(0px 18px 22px rgba(0, 0, 0, 0.75))",
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        ) : (
          <div
            style={{
              width: "100%",
              height: "100%",
              minHeight: 0,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              transform: `scale(${0.88 + 0.14 * itemScale})`,
            }}
          >
            {activeItem.imageFile && (
              <Img
                src={staticFile(activeItem.imageFile)}
                style={{
                  width: "92%",
                  height: "84%",
                  maxWidth: "92%",
                  maxHeight: "84%",
                  objectFit: "contain",
                  filter: "drop-shadow(0px 26px 32px rgba(0, 0, 0, 0.82))",
                }}
              />
            )}
            <div
              style={{
                marginTop: 24,
                color: "#FFFFFF",
                fontSize: 38,
                fontWeight: 800,
                textShadow: "0px 3px 12px rgba(0, 0, 0, 0.7)",
              }}
            >
              {activeItem.name}
            </div>
          </div>
        )}
      </div>

      {/* Pastki ixcham, ekranni to'smaydigan minimalistik satr */}
      <div
        style={{
          flexShrink: 0,
          backgroundColor: "rgba(18, 18, 21, 0.78)",
          borderRadius: 999,
          padding: "20px 36px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          border: "1px solid rgba(255, 255, 255, 0.14)",
          zIndex: 2,
        }}
      >
        <div style={{ color: "#F5F5F7", fontSize: 28, fontWeight: 700 }}>
          50% oldindan: <span style={{ color: "#E8C56B" }}>{fmt(prepay50Uzs)} so'm</span>
        </div>
        <div style={{ color: "#BDBDC4", fontSize: 24, fontWeight: 600 }}>
          To'liq: {fmt(totalPriceUzs)} so'm · Izohga «+»
        </div>
      </div>

      {/* Beat-drop transition overlay */}
      {beatDropDim > 0.01 ? (
        <AbsoluteFill
          style={{
            backgroundColor: `rgba(8, 8, 10, ${beatDropDim})`,
            pointerEvents: "none",
            zIndex: 5,
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
