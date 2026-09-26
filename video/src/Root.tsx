import React from 'react';
import {Composition} from 'remotion';
import {BenchyDemo} from './Scenes';

export const Root: React.FC = () => (
  <Composition
    id="BenchyDemo"
    component={BenchyDemo}
    durationInFrames={564}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{}}
  />
);
