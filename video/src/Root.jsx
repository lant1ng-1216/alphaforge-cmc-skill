import { Composition } from "remotion";
import { Intro } from "./Intro.jsx";
import { Outro } from "./Outro.jsx";

const FPS = 30;

export const Root = () => {
  return (
    <>
      <Composition
        id="Intro"
        component={Intro}
        durationInFrames={8 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="Outro"
        component={Outro}
        durationInFrames={8 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
