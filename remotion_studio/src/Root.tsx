import React from "react";
import { Composition } from "remotion";
import { LookReel, LookReelProps } from "./LookReel";

const defaultProps: LookReelProps = {
  shopBrand: "XAN SHOP",
  lookTitle: "Diplomatiya va Yuridika Qishki Old Money Kapsulasi",
  subtitleHook: "O'qish, ofis va jiddiy uchrashuvlar uchun",
  totalPriceUzs: 950000,
  prepay50Uzs: 475000,
  themeVariant: "editorial_light",
  audioFile: "",
  items: [
    { name: "To'q Ko'k Klassik Jun Blazer", priceUzs: 400000, imageFile: "" },
    { name: "To'q Qahva Kashmir Vodolazka", priceUzs: 305000, imageFile: "" },
    { name: "Grafit Klassik Drape Shim", priceUzs: 245000, imageFile: "" },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="LookReel"
      component={LookReel as unknown as React.FC<Record<string, unknown>>}
      durationInFrames={194}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={defaultProps as unknown as Record<string, unknown>}
      calculateMetadata={({ props }) => {
        const p = (props || defaultProps) as unknown as LookReelProps;
        const count = Math.max(1, (p.items || []).length);
        const framesPerItem = 48;
        const finaleFrames = 50;
        return {
          durationInFrames: count * framesPerItem + finaleFrames,
          fps: 30,
          width: 1080,
          height: 1920,
        };
      }}
    />
  );
};
